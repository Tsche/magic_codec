# pylint: disable=eval-used,exec-used

import ast as _ast
from dataclasses import dataclass
from importlib.machinery import PathFinder, SourceFileLoader
import os
from token import DEDENT, ENDMARKER, INDENT, NAME, NEWLINE, NUMBER, OP, STRING, COMMENT
from tokenize import detect_encoding, untokenize
from typing import Any, Generator, Optional
import re
import sys
import traceback

from magic_codec.util import Cancellation, Code, ParseError, Token, TokenStream, get_tokens


class _Code(Code):
    """ Tag type to mark code objects coming from the preprocessor """


class MacroDecorator(type):
    def __call__(cls, *args, **kwargs):
        ctor = super().__call__

        def wrap(code):
            nonlocal ctor
            return ctor(*args, **kwargs)(code)

        if not kwargs and len(args) == 1 and isinstance(args[0], _Code):
            # effectively forbids the first positional-only argument of the ctor to be
            # of type _Code, which should be fine since this is only used internally
            return ctor()(args[0])
        else:
            return wrap


class NodeTransformer(_ast.NodeTransformer, metaclass=MacroDecorator):
    def __call__(self, code: Code):
        new_tree = self.visit(code.ast)
        new_source = _ast.unparse(new_tree)

        yield from get_tokens(new_source)

        # ensure a new line after the new code segment
        # for some reason round-tripping messes with newlines
        yield Token(NEWLINE, '\n')


def macro(fnc=None, /, **kwargs):
    """ This decorator does nothing. It is only used to flag functions and classes as macros. """
    class Macro:
        def __init__(self, func):
            nonlocal kwargs
            self.fnc = func
            self.options = kwargs

        def __call__(self, *args, **kwds):
            return self.fnc(*args, **kwds)

    return Macro(fnc) if fnc else Macro


class MacroFileLoader(SourceFileLoader):
    def process_macros(self):
        print(self.path)

    def get_data(self, actual_path):
        if not os.path.exists(actual_path):
            return b''

        if not actual_path.endswith(".py"):
            # module has already been compiled
            self.process_macros()
            return super().get_data(actual_path)

        with open(actual_path, 'r', encoding='utf-8') as source:
            assert self.path == actual_path, "Actual path isn't the expected original module path, but ends in .py"
            self.process_macros()
            return source.read()


class MacroFinder(PathFinder):
    @staticmethod
    def uses_macro_codec(path):
        with open(path, 'rb') as source:
            encoding, *_ = detect_encoding(source.readline)
            return encoding == "magic.macro"

    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        if not (spec := super().find_spec(fullname, path, target)):
            return

        if not (spec.origin and isinstance(spec.loader, SourceFileLoader)):
            # we cannot process macros unless we have an origin
            return

        if cls.uses_macro_codec(spec.origin):
            spec.loader = MacroFileLoader(fullname, spec.origin)
            return spec


def install_import_hook():
    # This needs to be called within the macro preprocessor context
    # to allow importing macros from other modules, even if they
    # have already been compiled
    sys.meta_path.insert(0, MacroFinder())


MACRO_PREFIX = "__macro__"


class UnresolvedSymbol(Exception): 
    """ Raised when a symbol cannot be resolved in the context of the preprocessor. """


@dataclass
class Decorator:
    named_expression: list[Token]

    def to_tokens(self) -> Generator[Token, None, None]:
        ''' 
            '@' named_expression NEWLINE 
        '''
        yield Token(OP, '@')
        yield from self.named_expression
        yield Token(NEWLINE, '\n')

    @property
    def name(self):
        assert self.named_expression, "Invalid decorator"
        if self.named_expression[0].type != NAME:
            return None

        if len(self.named_expression) > 1 and self.named_expression[1] == (OP, '!'):
            return f"{MACRO_PREFIX}{self.named_expression[0].string}"

        return self.named_expression[0].string


@dataclass
class FunctionDefinition:
    name: str
    decorators: list[Decorator]
    code: list[Token]
    is_macro: bool = False


def parse_import(tokens: TokenStream, require_bang=False):
    with tokens.alt:
        first_token = tokens.expect((NAME, ["import!", "from!"] if require_bang else ["import", "from"]))
        return [first_token, *tokens.consume_line()]
    return None


def parse_assignment(tokens: TokenStream, require_bang: bool = False):
    with tokens.alt:
        name = tokens.expect((NAME, ...))
        if tokens.peek() == (OP, '!'):
            tokens.next()
            name = Token(NAME, f"{MACRO_PREFIX}{name.string}")
        elif require_bang:
            raise Cancellation

        op = tokens.expect((OP, '='))
        return [name, op, *transform_bang_names(TokenStream(tokens.consume_line()))]
    return None


def parse_decorator(tokens: TokenStream):
    with tokens.alt:
        tokens.expect((OP, '@'))
        if named_expression := tokens.consume_line(with_newline=False):
            return Decorator(named_expression)
        else:
            raise ParseError("named_expression expected after `@`")

    return None


def parse_function(tokens: TokenStream):
    with tokens.alt:
        decorators = []
        while decorator := parse_decorator(tokens):
            decorators.append(decorator)

        code = []
        is_macro = any(decorator.name == "macro" for decorator in decorators)

        while next_token := tokens.next():
            if next_token.type != NAME:
                raise Cancellation
            if next_token.string == 'macro':
                is_macro = True
            elif next_token.string == 'async':
                code.append(next_token)
            else:
                break

        if next_token != (NAME, ["class", "def"]):
            raise Cancellation
        code.append(next_token)

        name = tokens.expect((NAME, ...)).string
        if tokens.peek() == (OP, '!'):
            tokens.next()
            is_macro = True
            name = f"{MACRO_PREFIX}{name}"

        code.append(Token(NAME, name))
        line = tokens.consume_line(True)
        code.extend(line)
        if len(line) <= 2:
            raise Cancellation
        offset = line[-2] == (COMMENT, ...)
        if len(line) >= 2 + offset and line[-2 - offset] == (OP, ':'):
            # if the last token before the new line wasn't `:`
            # we can assume no indented block will follow, ie
            # def foo(): ...
            code.extend(tokens.consume_balanced((INDENT, ...), (DEDENT, ...)))

        return FunctionDefinition(name, decorators, code, is_macro)
    return None


def transform_bang_names(tokens: TokenStream):
    for token in tokens:
        if token.type == NAME and tokens.peek() == (OP, '!'):
            tokens.next()
            name = MACRO_PREFIX + token.string
            yield Token(NAME, name)
            continue
        yield token


def synthesize_call(function: str | list[Token], expression: list[Token]):
    name = [Token(NAME, function)] if isinstance(function, str) else function
    return [*name, Token(OP, '('), *expression, Token(OP, ')')]


def synthesize_call_chain(calls: list[list[Token]], args: list[Token], convert_to: Optional[str] = None):
    if not calls:
        return synthesize_call(convert_to, args) if convert_to else args
    call = synthesize_call(calls[0], synthesize_call_chain(calls[1:], args, convert_to))
    return synthesize_call(convert_to, call) if convert_to else call


def synthesize_constant(value: Any):
    if value is None:
        return
    elif isinstance(value, bool):
        yield Token(NAME, str(value))
    elif isinstance(value, (int, float)):
        yield Token(NUMBER, str(value))
    elif isinstance(value, str):
        try:
            node = _ast.parse(value, mode="eval")
            if isinstance(node.body, _ast.Constant):
                yield Token(STRING, value)
            elif isinstance(node.body, _ast.Name):
                yield Token(NAME, value)
            else:
                # string contains more than one token - insert all of them into the token stream
                raise SyntaxError
        except SyntaxError:
            yield from get_tokens(value)[:-1]
    else:
        # couldn't find something to replace the constant with
        # assume a replacement wasn't desired
        yield from get_tokens(value)[:-1]


def handle_exception(exc_type, exc_value, exc_traceback):
    def demangle_names(text):
        return re.sub("__macro__([a-zA-Z_]+)", "\\1!", text)

    if exc_type is NameError:
        for line in traceback.format_exception(exc_value):
            sys.stderr.write(demangle_names(line))


class Interpreter:
    __default_globals = {
        # 'tokenize': tokenize,
        # 'ast': _ast,
        'Code': Code,
        'MacroDecorator': MacroDecorator,
        'NodeTransformer': NodeTransformer,
        'macro': macro,
        'get_tokens': get_tokens,
    }

    def __init__(self):
        self.globals: dict[str, Any] = self.__default_globals
        self.macros: dict[str, Any] = {}
        self.install_excepthook(handle_exception)
    
    def install_excepthook(self, hook: callable):
        exec("import sys; sys.excepthook=__excepthook", {'__excepthook': hook})

    def resolve_symbol(self, name: str):
        try:
            return self.macros.get(name, self.globals[name])
        except KeyError as exc:
            raise UnresolvedSymbol(f"Cannot find {name}") from exc

    def reset(self):
        self.globals = self.__default_globals
        self.macros = {}

    def exec(self, code: list[Token], locals: Optional[dict[str, Any]] = None):
        exec(untokenize(code), self.globals, locals or self.macros)

    def eval(self, code: list[Token], locals: Optional[dict[str, Any]] = None):
        return eval(untokenize(code), self.globals, locals or self.macros)


class MacroProcessor:
    __default_globals = {
        # 'tokenize': tokenize,
        # 'ast': _ast,
        'Code': Code,
        'MacroDecorator': MacroDecorator,
        'NodeTransformer': NodeTransformer,
        'macro': macro,
        'get_tokens': get_tokens,
    }

    def __init__(self):
        self.globals: dict[str, Any] = self.__default_globals
        self.macros: dict[str, Any] = {}
        self.install_excepthook(handle_exception)

    def install_excepthook(self, hook: callable):
        exec("import sys; sys.excepthook=__excepthook", {'__excepthook': hook})

    def resolve_symbol(self, name: str):
        try:
            return self.macros.get(name, self.globals[name])
        except KeyError as exc:
            raise UnresolvedSymbol(f"Cannot find {name}") from exc

    def reset(self):
        self.globals = self.__default_globals
        self.macros = {}

    def exec(self, code: list[Token], locals: Optional[dict[str, Any]] = None):
        exec(untokenize(code), self.globals, locals or self.macros)

    def eval(self, code: list[Token], locals: Optional[dict[str, Any]] = None):
        return eval(untokenize(code), self.globals, locals or self.macros)

    def apply_macros(self, code: list[Token], macros: list[list[Token]]):
        call = synthesize_call_chain(macros, args=[Token(NAME, "__magic_macro_code_object")], convert_to="_Code")
        call_locals = {**self.macros,
                       '__magic_macro_code_object': code,
                       '_Code': _Code}

        return self.eval(call, call_locals).tokens

    def transform_function(self, decorated: FunctionDefinition):
        tokens = TokenStream(decorated.code)

        # evaluate macros in code
        code = list(self.transform_code(tokens))

        # apply macro decorators
        decorators: list[Token] = []
        macro_decorators: list[list[Token]] = []

        for decorator in decorated.decorators:
            if decorator.name == "macro":
                decorated.is_macro = True
            elif decorator.name in self.macros:
                decorator_code = list(transform_bang_names(TokenStream(decorator.named_expression)))
                macro_decorators.append(decorator_code)
                continue
            else:
                if len(decorator.named_expression) > 1 and decorator.named_expression[1] == (OP, "!"):
                    raise UnresolvedSymbol(f"Could not resolve {decorator.name}")

            decorators.extend(decorator.to_tokens())

        code = [*decorators, *code]
        yield from self.apply_macros(code, macro_decorators)

    def transform_code(self, tokens: TokenStream):
        for current in tokens:
            if current.type == NAME:
                name = current.string
                diagnose_failure = False
                if tokens.peek() == (OP, '!'):
                    tokens.next()
                    # transform name directly
                    name = f"{MACRO_PREFIX}{current.string}"
                    diagnose_failure = True

                if name in self.macros:
                    if tokens.peek() == (OP, '('):
                        # function-like macro call
                        args = tokens.consume_balanced((OP, '('), (OP, ')'))

                        result = self.eval([(NAME, name), *args])
                        yield from synthesize_constant(result)
                    else:
                        yield from synthesize_constant(self.macros[name])
                    continue

                elif diagnose_failure:
                    raise UnresolvedSymbol(f"Could not resolve {name}")

            yield current

    def transform(self, tokens: TokenStream):
        level = 0
        while (current := tokens.peek()) and current.type != ENDMARKER:

            # track current indentation
            if current == (INDENT, ...):
                level += 1
                yield tokens.next()
                continue
            elif current == (DEDENT, ...):
                level -= 1
                yield tokens.next()
                continue

            macro_context = False
            if level == 0 and current == (NAME, "macro"):
                tokens.next()
                macro_context = True

            if level == 0 and (code := parse_assignment(tokens, require_bang=not macro_context)):
                self.exec(code)

            elif level == 0 and (code := parse_import(tokens, require_bang=not macro_context)):
                self.exec(code, self.globals)

            elif fnc := parse_function(tokens):
                code = self.transform_function(fnc)
                if level == 0 and (fnc.is_macro or macro_context):
                    self.exec(code)
                else:
                    yield from code
            else:
                # ensure next iteration starts on a new line
                line = tokens.consume_line(True)
                yield from self.transform_code(TokenStream(line))
        yield Token(ENDMARKER, '')


# @cache
def preprocess(data: str):
    print("!!!!!!!!!!!")
    tokens    = TokenStream(Code(data).tokens)
    processor = MacroProcessor()
    new_code  = Code(list(processor.transform(tokens)))
    return new_code.string
