# pylint: disable=eval-used,exec-used

from abc import ABC, abstractmethod
import ast as _ast
from dataclasses import dataclass
from importlib.machinery import PathFinder, SourceFileLoader
import os
from pathlib import Path
from token import DEDENT, ENDMARKER, INDENT, NAME, NEWLINE, NL, NUMBER, OP, STRING, COMMENT
from tokenize import detect_encoding
from typing import Any, Callable, Iterable, Optional
import re
import sys
import traceback
from magic_codec.util import Cancellation, Code, ParseError, Token, TokenStream, Untokenizer, tokenize, untokenize


class _Code(Code):
    """ Tag type to mark code objects coming from the preprocessor """


class NodeTransformerMeta(type):
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


class NodeTransformer(_ast.NodeTransformer, metaclass=NodeTransformerMeta):
    def __call__(self, code: Code):
        new_tree = self.visit(code.ast)
        new_source = _ast.unparse(new_tree)

        yield from tokenize(new_source, False)

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

    def get_data(self, path: str) -> bytes:
        if not os.path.exists(path):
            return b''

        if not path.endswith(".py"):
            # module has already been compiled
            self.process_macros()
            return super().get_data(path)

        with open(path, 'rb') as source:
            assert self.path == path, "Actual path isn't the expected original module path, but ends in .py"
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


class Interpreter:
    __default_globals = {
        # 'tokenize': tokenize,
        # 'ast': _ast,
        'Code': Code,
        'NodeTransformer': NodeTransformer,
        'macro': macro,
        'tokenize': tokenize,
        'untokenize': untokenize,
        '__magic_macro_state': {}
    }

    def __init__(self):
        self.globals: dict[str, Any] = self.__default_globals
        self.macros: dict[str, Any] = {}
        # self.install_excepthook(handle_exception)

    def install_excepthook(self, hook: Callable):
        code = "import sys; sys.excepthook=__excepthook"
        self.exec(tokenize(code), {'__excepthook': hook})

    def reset(self):
        self.globals = self.__default_globals
        self.macros = {}

    def exec(self, code: Iterable[Token], locals=None):
        exec(untokenize(code), self.globals, locals or self.globals)

    def eval(self, code: Iterable[Token], locals=None):
        code: str = untokenize(code)
        from colorama import Fore
        print("evaluating: ", Fore.GREEN + code + Fore.RESET)

        return eval(code, self.globals, locals or self.globals)

    def apply_macros(self, code: Iterable[Token], macros: list[Iterable[Token]]):
        call = synthesize_call_chain(macros, args=[Token(NAME, "__magic_macro_code_object")], convert_to="_Code")
        call_locals = {'__magic_macro_code_object': code,
                       '_Code': Code}
        return self.eval(call, call_locals).tokens

@dataclass
class Fragment(ABC):
    is_macro: bool

    @abstractmethod
    def get_code(self) -> Iterable[Token]:
        ...

    @abstractmethod
    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        ...


def get_code(fragment: Fragment | Iterable[Fragment]) -> Iterable[Token]:
    if isinstance(fragment, Fragment):
        yield from fragment.get_code()
    else:
        for frag in fragment:
            yield from frag.get_code()


def evaluate(interpreter: Interpreter, fragment: Fragment | Iterable[Fragment]) -> Iterable[Token]:
    if isinstance(fragment, Fragment):
        yield from fragment.evaluate(interpreter)
    else:
        for frag in fragment:
            yield from frag.evaluate(interpreter)


@dataclass
class Decorator:
    named_expression: list[Fragment]
    is_macro: bool = False
    is_macro_keyword: bool = False

    def get_code(self) -> Iterable[Token]:
        yield Token(OP, '@')
        for fragment in self.named_expression:
            yield from fragment.get_code()
        yield Token(NEWLINE, '\n')

@dataclass
class FunctionDefinition(Fragment):
    decorators: list[Decorator]
    head: list[Fragment]
    body: list[Fragment]

    def get_code(self) -> Iterable[Token]:
        for item in (*self.decorators, *self.head, *self.body):
            yield from item.get_code()

    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        assert not self.is_macro, "New macros cannot appear here"

        macro_decorators = [get_code(decorator.named_expression) for decorator in self.decorators if decorator.is_macro]
        decorators = [token for decorator in self.decorators if not decorator.is_macro
                            for token in get_code(decorator.named_expression)]
        head = get_code(self.head)
        body = evaluate(interpreter, self.body)

        if macro_decorators:
            body = interpreter.apply_macros(body, macro_decorators)

        return [*decorators, *head, *body]


@dataclass
class MacroInvocation(Fragment):
    name: str
    args: list[Token]

    def get_code(self) -> Iterable[Token]:
        yield Token(NAME, self.name)
        yield from self.args

    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        if self.is_macro:
            yield from self.get_code()
        else:
            result = interpreter.eval(self.get_code())
            yield from synthesize_constant(result)


@dataclass
class MacroStatement(Fragment):
    macro: MacroInvocation
    code: list[Fragment]

    def get_code(self) -> Iterable[Token]:
        yield from get_code(self.macro)
        yield Token(OP, ':')
        yield from get_code(self.code)

    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        code = evaluate(interpreter, self.code)
        yield from interpreter.apply_macros(code, [get_code(self.macro)])

@dataclass
class CodeFragment(Fragment):
    code: list[Token]

    def get_code(self) -> Iterable[Token]:
        yield from self.code

    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        yield from self.code


class Parser(TokenStream):
    def __init__(self, iterable: Iterable[Token], indent: int = 0):
        super().__init__(iterable)
        self.indent: int = indent

    def parse_macro_fragment(self):
        with self.alt:
            # imports within the preprocessor
            kind = self.expect((NAME, ["import", "from"]))
            self.expect((OP, '!'))
            # TODO handle bang names
            return [CodeFragment(True, [kind, *self.consume_line()])]

        with self.alt:
            # object-like macro
            if not (name := self.parse_macro_name()):
                raise Cancellation
            op = self.expect((OP, '='))
            return [CodeFragment(True, [Token(NAME, name), op]), *Parser(self.consume_line()).parse_line(True)]

    def parse_decorator(self):
        with self.alt:
            self.expect((OP, '@'))
            if named_expression := self.consume_line(with_newline=False):
                parser = Parser(named_expression)
                is_macro = False
                is_macro_keyword = False
                with parser.alt:
                    name = parser.expect((NAME, ...))
                    if name.string == "macro":
                        is_macro = True
                        is_macro_keyword = True

                    with parser.alt:
                        parser.expect((OP, '!'))
                        is_macro = True

                parser.reset(0)
                return Decorator(list(parser.parse_line()), is_macro, is_macro_keyword)
            raise ParseError("named_expression expected after `@`")

        return None

    def parse_suite(self) -> Iterable[Token]:
        if self.peek().type in (COMMENT, NL, NEWLINE):
            yield from self.consume_while(([COMMENT, NL, NEWLINE], ...))
            yield from self.consume_balanced((INDENT, ...), (DEDENT, ...))
        else:
            yield from self.consume_line()

    def parse_decorators(self):
        while decorator := self.parse_decorator():
            yield decorator

    def parse_function_head(self):
        head = []
        if token := self.maybe((NAME, "async")):
            head.append(token)

        head.append(self.expect((NAME, ["class", "def"])))

        name = self.expect((NAME, ...)).string
        is_macro = False
        if self.maybe((OP, '!')):
            is_macro = True

        if is_macro:
            # always mangle macro names
            name = f"{MACRO_PREFIX}{name}"

        head.append(Token(NAME, name))
        # args
        if self.peek() == (OP, '('):
            head.extend(self.consume_balanced((OP, '('), (OP, ')')))

        if self.peek() == (OP, '->'):
            # return type annotation
            head.extend(self.consume_until((OP, ':')))
        head.append(self.expect((OP, ':')))
        return is_macro, head

    def parse_function(self):
        with self.alt:
            decorators = list(self.parse_decorators())
            is_macro, head = self.parse_function_head()
            is_macro |= any(decorator.is_macro_keyword for decorator in decorators)

            body = self.parse_suite()
            # expand macro invocations in the head
            head = list(Parser(head).parse_line())
            # expand macros
            body = list(Parser(body, indent=self.indent).parse())

            return FunctionDefinition(is_macro, decorators, head, body)
        return None

    def parse_macro_statement(self):
        with self.alt:
            macro = self.parse_macro_invocation(True)
            self.expect((OP, ':'))
            body: list[Fragment] = list(Parser(self.parse_suite(), indent=self.indent).parse())
            return MacroStatement(False, macro, body)
        return None

    def parse(self):
        while (current := self.peek()) and current.type != ENDMARKER:
            # track current indentation
            if current.type == INDENT:
                self.indent += 1
                yield CodeFragment(False, [self.next()])
            elif current.type == DEDENT:
                self.indent -= 1
                yield CodeFragment(False, [self.next()])
            elif self.indent == 0 and (code := self.parse_macro_fragment()):
                # macro import or object-like macro
                yield from code
            elif fnc := self.parse_function():
                if self.indent != 0 and fnc.is_macro:
                    # function-like macro only allowed at module scope
                    fnc.is_macro = False
                yield fnc
            elif statement := self.parse_macro_statement():
                yield statement
            else:
                # ensure next iteration starts on a new line
                yield from self.parse_line()

    def parse_macro_name(self):
        name = self.expect((NAME, ...)).string
        self.expect((OP, "!"))
        return f"{MACRO_PREFIX}{name}"

    def parse_macro_invocation(self, is_macro: bool = False):
        name = self.parse_macro_name()
        args = []
        if self.peek() == (OP, '('):
            # function-like macro call
            args = self.consume_balanced((OP, '('), (OP, ')'))
            # TODO descend into arg list to find macros to replace there?
            # At this point we can't know whether the macro wants raw tokens
            # and we don't yet know whether it exists or not
        return MacroInvocation(is_macro, name, args)

    def parse_line(self, is_macro=False):
        fragment = []
        while current := self.peek():
            if current.type in (NL, NEWLINE):
                fragment.append(self.next())
                break

            if current.type != NAME:
                fragment.append(self.next())
                continue

            with self.alt:
                invocation = self.parse_macro_invocation(is_macro)
                if fragment:
                    yield CodeFragment(is_macro, fragment)
                    fragment = []
                yield invocation
                continue

            fragment.append(self.next())

        if fragment:
            yield CodeFragment(is_macro, fragment)


def synthesize_call(function: str | Iterable[Token], expression: list[Token]):
    name = [Token(NAME, function)] if isinstance(function, str) else function
    return [*name, Token(OP, '('), *expression, Token(OP, ')')]


def synthesize_call_chain(calls: list[Iterable[Token]], args: list[Token], convert_to: Optional[str] = None) -> list[Token]:
    call = synthesize_call(calls[0], synthesize_call_chain(calls[1:], args, convert_to)) if calls else args
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
            yield from tokenize(value)
    else:
        # couldn't find something to replace the constant with
        # assume a replacement wasn't desired
        yield from tokenize(value)


def parse(tokens: TokenStream):
    macro_code: list[Token] = []
    code: list[Fragment] = []
    parser = Parser(tokens)
    for node in parser.parse():
        if isinstance(node, (Fragment)) and node.is_macro:
            macro_code.extend(node.get_code())
        else:
            code.append(node)

    return macro_code, code


def transform(macro_code: list[Token], code: list[Fragment]) -> Iterable[Token]:
    interpreter = Interpreter()
    interpreter.exec(macro_code)
    for fragment in code:
        yield from fragment.evaluate(interpreter)


def handle_exception(exc_type, exc_value, exc_traceback):
    def demangle_names(text):
        return re.sub("__macro__([a-zA-Z_]+)", "\\1!", text)

    if exc_type is NameError:
        for line in traceback.format_exception(exc_value):
            sys.stderr.write(demangle_names(line))


def print_syntax(tokens: TokenStream):
    from colorama import Fore
    untokenizer = Untokenizer()

    def print_colored_if(condition, code, color, color2=Fore.RESET):
        print(f"{color if condition else color2}{untokenizer.untokenize(code)}{Fore.RESET}", end="")

    def print_rec(items, is_macro=False):
        for node in items:
            if isinstance(node, FunctionDefinition):
                for decorator in node.decorators:
                    print_colored_if(decorator.is_macro, decorator.get_code(),
                                     Fore.BLUE if node.is_macro else Fore.CYAN,
                                     Fore.GREEN)
                print_rec(node.head, node.is_macro or is_macro)
                print_rec(node.body, node.is_macro or is_macro)
            elif isinstance(node, CodeFragment):
                print_colored_if(node.is_macro or is_macro, node.get_code(), Fore.GREEN)
            elif isinstance(node, (MacroInvocation, MacroStatement)):
                print_colored_if(node.is_macro or is_macro, node.get_code(), Fore.BLUE, Fore.CYAN)
            else:
                raise ParseError(f"Unexpected node {node}")

    parser = Parser(tokens)
    print_rec(parser.parse())
    print()


# @cache
def preprocess(data: str):
    tokens    = TokenStream(Code(data).tokens)
    new_code  = Code(list(transform(*parse(tokens))))
    return new_code.string


def main():
    import argparse
    args_parser = argparse.ArgumentParser("magic_macro")
    args_parser.add_argument("source")
    args_parser.add_argument("--syntax-only", action="store_true")
    args_parser.add_argument("--preprocessor", action="store_true")
    args_parser.add_argument("--replacements", action="store_true")
    args = args_parser.parse_args()

    source = Path(args.source)
    tokens = TokenStream(Code(source.read_text(encoding='utf-8')).tokens)

    if args.syntax_only:
        print_syntax(tokens)
        return

    macro_source, replacements = parse(tokens)
    if args.preprocessor:
        print(untokenize(macro_source))
    elif args.replacements:
        print(replacements)
    else:
        transformed = list(transform(macro_source, replacements))
        print(untokenize(transformed))


if __name__ == "__main__":
    main()
