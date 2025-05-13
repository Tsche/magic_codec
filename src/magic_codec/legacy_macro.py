# pylint: disable=eval-used,exec-used

from abc import ABC, abstractmethod
import ast as _ast
from dataclasses import dataclass
from importlib.machinery import PathFinder, SourceFileLoader
import os
from pathlib import Path
from token import DEDENT, ENDMARKER, INDENT, NAME, NEWLINE, NL, NUMBER, OP, STRING, COMMENT
from tokenize import detect_encoding
from typing import Any, Callable, Generator, Iterable, Optional
import re
import sys
import traceback
from keyword import iskeyword, issoftkeyword
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

def macro(fnc=None, /, eval_args=False, **kwargs):
    """ This decorator does nothing. It is only used to flag functions and classes as macros. """

    class Macro:
        def __init__(self, func):
            nonlocal kwargs
            self.fnc = func
            self.options = kwargs

        def __call__(self, *args, **kwds):
            if eval_args and not kwargs and len(args) == 1 and isinstance(args[0], Code):
                # only received a single argument of code type
                code_object: Code = args[0]
                call = synthesize_call([Token(NAME, "self"), Token(OP, '.'), Token(NAME, 'fnc')], 
                                       list(code_object.tokens))
                return eval(untokenize(call), globals(), locals())
            return self.fnc(*args, **kwds)

    return Macro(fnc) if fnc else Macro


class MacroFileLoader(SourceFileLoader):
    def __init__(self, fullname: str, path: str, macro_only: bool = False) -> None:
        super().__init__(fullname, path)
        self.macro_only = macro_only

    def process_macros(self):
        print(self.path)

    def set_data(self, path: str, data, *, _mode: int = 438) -> None:
        print("set: ", path)
        return super().set_data(path, data, _mode=_mode)

    def get_data(self, path: str) -> bytes:
        print("get: ", path)
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
        macro_only = False
        parts = fullname.split('.')
        if parts[-1].startswith(MACRO_PREFIX):
            # the module was imported via name! bang-name
            # => we're only interested in this module's macros
            parts[-1] = parts[-1].removeprefix(MACRO_PREFIX)
            fullname = '.'.join(parts)
            macro_only = True

        if not (spec := super().find_spec(fullname, path, target)):
            return

        if not (spec.origin and isinstance(spec.loader, SourceFileLoader)):
            # we cannot process macros unless we have an origin
            return

        if cls.uses_macro_codec(spec.origin):
            spec.loader = MacroFileLoader(fullname, spec.origin, macro_only)
            return spec


MACRO_PREFIX = "__macro__"


def mangle(name: str, force: bool = False) -> str:
    # to allow keywords to be used as macro names, they must be mangled
    if iskeyword(name) or issoftkeyword(name) or force:
        return f"{MACRO_PREFIX}{name}"
    return name


def demangle(text):
    return re.sub(f"{MACRO_PREFIX}(\\w+)", "\\1!", text)


def install_import_hook():
    # This needs to be called within the macro preprocessor context
    # to allow importing macros from other modules, even if they
    # have already been compiled
    sys.meta_path.insert(0, MacroFinder())


def handle_exception(exc_type, exc_value, exc_traceback):
    if exc_type is NameError:
        for line in traceback.format_exception(exc_value):
            sys.stderr.write(demangle(line))


class UnresolvedSymbol(Exception): 
    """ Raised when a symbol cannot be resolved in the context of the preprocessor. """


class Interpreter:
    __default_globals = {
        # 'tokenize': tokenize,
        # 'ast': _ast,
        "__name__": "__main__",
        'Token': Token,
        'Code': Code,
        'NodeTransformer': NodeTransformer,
        'macro': macro,
        'tokenize': macro(tokenize, eval_args=True),
        'untokenize': macro(untokenize, eval_args=True)
    }

    def __init__(self):
        self.globals: dict[str, Any] = self.__default_globals
        self.macros: dict[str, Any] = {}
        # self.install_excepthook(handle_exception)
        self.install_importhook()


    def execute_fnc(self, fnc, *args, **kwargs):
        self.exec(tokenize("__fn(*__args, **__kwargs)"), {'__fn': fnc, '__args': args, '__kwargs': kwargs})

    def setup_imports(self, source_path: Path):
        self.globals["__file__"] = source_path
        
        # def modify_path(path):
        #     import sys
        #     sys.path.insert(0, str(path))
        
        # self.execute_fnc(modify_path, source_path.parent.absolute())

    def install_excepthook(self, hook: Callable):
        def install_hook(hook_):
            import sys
            sys.excepthook = hook_
        self.execute_fnc(install_hook, hook)

    def install_importhook(self):
        self.execute_fnc(install_import_hook)

    def reset(self):
        self.globals = self.__default_globals
        self.macros = {}

    def exec(self, tokens: Iterable[Token], locals=None):
        code = untokenize(tokens)
        exec(code, self.globals, locals or self.globals)

    def eval(self, tokens: Iterable[Token], locals=None):
        code = untokenize(tokens)
        return eval(code, self.globals, locals or self.globals)

    def apply_macros(self, code: Iterable[Token], macros: Iterable[Iterable[Token]]):
        call = synthesize_call_chain(macros, args=[Token(NAME, "__magic_macro_code_object")], convert_to="_Code")
        call_locals = {'__magic_macro_code_object': _Code(list(code)),
                       '_Code': _Code}
        return self.eval(call, call_locals).tokens


def synthesize_token_list(tokens: list[Token], raw = False):
    cast_to = "" if raw else "Token"
    token_list = ', '.join(f"{cast_to}({token.type},{token.string!r})" for token in tokens)
    code = f"[{token_list}]" if raw else f"Code([{token_list}])"
    return list(tokenize(code))

def synthesize_call(function: str | Iterable[Token], expression: Iterable[Token]) -> list[Token]:
    name = [Token(NAME, function)] if isinstance(function, str) else function
    return [*name, Token(OP, '('), *expression, Token(OP, ')')]


def synthesize_call_chain(calls: Iterable[Iterable[Token]], args: list[Token], convert_to: Optional[str] = None) -> list[Token]:
    calls = list(calls)
    call = synthesize_call(calls[0], synthesize_call_chain(calls[1:], args, convert_to)) if calls else args
    return synthesize_call(convert_to, call) if convert_to else call


def synthesize_constant(value: Any):
    if value is None:
        return
    elif isinstance(value, Token):
        if value.string == "None":
            return
        yield value
    elif isinstance(value, tuple):
        if len(value) != 2:
            raise SyntaxError("Can only return (str, int) 2-tuples in place of tokens")
        if value[1] == "None":
            return
        yield Token(int(value[0]), str(value[1]))
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
    elif isinstance(value, (list, Generator)):
        # directly inject tokens into token stream
        for item in value:
            if not isinstance(item, (Token, tuple)):
                raise SyntaxError("Expected list or generator of tokens to directly inject into the token stream")
            yield from synthesize_constant(item)
    else:
        # couldn't find something to replace the constant with
        raise SyntaxError(f"Unexpected macro return value {type(value)}")


@dataclass
class Fragment(ABC):
    is_macro: bool

    @abstractmethod
    def get_code(self, drop_comments=False) -> Iterable[Token]:
        ...

    @abstractmethod
    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        ...


def get_code(fragment: Fragment | Iterable[Fragment], drop_comments = False) -> Iterable[Token]:
    if isinstance(fragment, Fragment):
        yield from fragment.get_code(drop_comments)
    else:
        for frag in fragment:
            yield from frag.get_code(drop_comments)


def evaluate(interpreter: Interpreter, fragment: Fragment | Iterable[Fragment]) -> Iterable[Token]:
    if isinstance(fragment, Fragment):
        yield from fragment.evaluate(interpreter)
    else:
        for frag in fragment:
            yield from frag.evaluate(interpreter)


@dataclass
class CodeFragment(Fragment):
    code: list[Token]

    def get_code(self, drop_comments = False) -> Iterable[Token]:
        for token in self.code:
            if token.type != COMMENT:
                # unconditionally yield everything that isn't a comment
                yield token
            elif not drop_comments:
                # only yield comments if instructed to do so
                yield token

    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        yield from self.get_code()


@dataclass
class Decorator:
    named_expression: CodeFragment
    is_macro: bool = False
    is_macro_keyword: bool = False

    def get_code(self, drop_comments = False) -> Iterable[Token]:
        yield Token(OP, '@')
        yield from self.named_expression.get_code(drop_comments)


@dataclass
class FunctionDefinition(Fragment):
    decorators: list[Decorator | CodeFragment]
    head: list[Fragment]
    body: list[Fragment]

    def get_code(self, drop_comments = False) -> Iterable[Token]:
        for item in (*self.decorators, *self.head, *self.body):
            yield from item.get_code(drop_comments)

    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        macro_decorators: list[list[Token]] = []
        decorators: list[Token] = []
        for decorator in self.decorators:
            if isinstance(decorator, Decorator) and decorator.is_macro:
                # make sure to drop comments from macro decorators
                code = get_code(decorator.named_expression, True)
                # TODO expand macro names
                macro_decorators.append(list(code))
            else:
                # never treat comments etc as macro code
                decorators.extend(decorator.get_code())

        head = list(get_code(self.head))
        body = list(evaluate(interpreter, self.body))

        if macro_decorators:
            body = interpreter.apply_macros(body, macro_decorators)

        return [*decorators, *head, *body]


@dataclass
class MacroInvocation(Fragment):
    name: str
    args: list[Token]

    def get_code(self, drop_comments = False) -> Iterable[Token]:
        yield Token(NAME, self.name)
        if self.args:
            yield Token(OP, '(')
            yield from synthesize_token_list(self.args[1:-1])
            yield Token(OP, ')')

    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        if self.args:
            result = interpreter.apply_macros(self.args[1:-1], [[Token(NAME, self.name)]])
        else:
            result = interpreter.eval([Token(NAME, self.name)])
        yield from synthesize_constant(result)


@dataclass
class MacroStatement(Fragment):
    macro: MacroInvocation
    code: list[Fragment]

    def get_code(self, drop_comments = False) -> Iterable[Token]:
        yield from get_code(self.macro, drop_comments)
        yield Token(OP, ':')
        yield from get_code(self.code, drop_comments)

    def evaluate(self, interpreter: Interpreter) -> Iterable[Token]:
        code = evaluate(interpreter, self.code)
        yield from interpreter.apply_macros(code, [self.macro.get_code(True)])




class Parser(TokenStream):
    def __init__(self, iterable: Iterable[Token], indent: int = 0):
        super().__init__(iterable)
        self.indent: int = indent

    def parse_macro_name(self):
        name = self.expect((NAME, ...)).string
        self.expect((OP, "!"))
        return mangle(name)

    def parse_suite(self) -> Iterable[Token]:
        if self.peek().type in (COMMENT, NL, NEWLINE):
            yield from self.consume_while(([COMMENT, NL, NEWLINE], ...))
            yield from self.consume_balanced((INDENT, ...), (DEDENT, ...))
        else:
            yield from self.consume_line()

    def parse_decorator(self):
        with self.alt:
            self.expect((OP, '@'))
            if raw_expression := self.consume_line(with_newline=True):
                parser = Parser(raw_expression)
                is_macro = False
                is_macro_keyword = False

                expr = []
                with parser.alt:
                    name = parser.expect((NAME, ...))
                    if name.string == "macro":
                        # special case `macro` decorator to mark functions as macros
                        #! do not flag this is_macro, otherwise it will be applied early
                        is_macro = False
                        is_macro_keyword = True

                    with parser.alt:
                        # could be a macro
                        parser.expect((OP, '!'))
                        is_macro = True

                    #? note that PEP 614 (https://peps.python.org/pep-0614/) significantly lifted the restrictions
                    #? on what can appear in a decorator expression. In future versions the macro preprocessor
                    #? could properly parse named expressions to look for macro invocations.
                    expr.append(name)

                # consume the rest of the line
                # TODO: expand macro invocations in decorator args?
                expr.extend(parser.consume_line())
                return Decorator(CodeFragment(is_macro, expr), is_macro, is_macro_keyword)
            raise ParseError("named_expression expected after `@`")
        
        with self.alt:
            # decorators might be interleaved with comments, make sure to parse these as well
            if self.peek().type == COMMENT:
                return CodeFragment(False, self.consume_line())
            return CodeFragment(False, [self.expect((COMMENT, ...))])

        return None

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
            # make sure to only ever mangle macro names
            name = mangle(name)

        head.append(Token(NAME, name))
        # args
        if self.peek() == (OP, '('):
            # TODO expand macros in default arguments?
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
            is_macro |= any(isinstance(decorator, Decorator) and decorator.is_macro_keyword for decorator in decorators)

            body = list(self.parse_suite())
            # expand macro invocations in the head
            head = list(Parser(head).parse_line())
            # expand macros in the body
            body = list(Parser(body, indent=self.indent).parse())

            return FunctionDefinition(is_macro, decorators, head, body)
        return None
 
    def parse_import(self):
        with self.alt:
            # imports within the preprocessor
            is_macro = False
            
            kind = self.expect((NAME, ["import", "from"])).string
            if self.maybe((OP, '!')):
                is_macro = True
            
            package = []
            # parse package
            while current := self.peek():
                if kind == "from" and current == (NAME, "import"):
                    # consume "import"
                    self.next()
                    if self.maybe((OP, '!')):
                        is_macro = True
                    break
                
                if current.type in (NL, NEWLINE):
                    break

                package.append(self.next())
            
            symbols = []
            if kind == "from":
                # parse symbol list
                ...
            # TODO handle bang names, handle `as`, handle comma
            symbols = self.consume_line()

            code = [Token(NAME, kind)]
            code.extend(package)
            if kind == "from":
                code.append(Token(NAME, "import"))
            code.extend(symbols)

            return [CodeFragment(is_macro, code)]
        return None

    def parse_macro_statement(self):
        with self.alt:
            name = self.parse_macro_name()
            macro = self.parse_macro_invocation(name, True)
            self.expect((OP, ':'))
            body: list[Fragment] = list(Parser(self.parse_suite(), indent=self.indent).parse())
            return MacroStatement(False, macro, body)

        return None

    def parse_macro_invocation(self, name: str, is_macro: bool = False):
        args = []
        if self.peek() == (OP, '('):
            # function-like macro call
            args = self.consume_balanced((OP, '('), (OP, ')'))
            # TODO descend into arg list to find macros to replace there?
            # At this point we can't know whether the macro wants raw tokens
            # and we don't yet know whether it exists or not
        return MacroInvocation(is_macro, name, args)

    def parse_token_literal(self):
        with self.alt:
            self.expect((OP, '`'))
            multiline = False

            code = []
            first = self.next()
            if first == (OP, '`'):
                if self.peek() == (OP, '`'):
                    self.next()
                    self.next()
                    multiline = True
                else:
                    return CodeFragment(False, synthesize_token_list([], True))
                    # return CodeFragment(False, [Token(NAME, "tokenize"), Token(OP, '('), Token(OP, '"'), Token(OP, '"'), Token(OP, ')')])
            else:
                code.append(first)
            
            while current := self.next():
                if current == (OP, '`'):
                    if multiline:
                        self.expect((OP, '`'))
                        self.expect((OP, '`'))
                    return CodeFragment(False, synthesize_token_list(code, True))
                    # return CodeFragment(False, [Token(NAME, "tokenize"), Token(OP, '('), Token(STRING, f'"""{untokenize(code)}"""'), Token(OP, ')')])
                elif not multiline and current.type in (NEWLINE, NL):
                    # unexpected newline
                    raise Cancellation
                else:
                    code.append(current)
        return None

    def parse_line(self, is_macro=False):
        fragment = []
        def push_partial():
            nonlocal fragment, is_macro
            if fragment:
                yield CodeFragment(is_macro, fragment)
                fragment = []

        while current := self.peek():
            if current.type in (NL, NEWLINE):
                fragment.append(self.next())
                break

            if token_lit := self.parse_token_literal():
                yield from push_partial()
                yield token_lit

            if current.type != NAME:
                fragment.append(self.next())
                continue

            with self.alt:
                name = self.parse_macro_name()
                invocation = self.parse_macro_invocation(name, is_macro)
                yield from push_partial()
                yield invocation
                continue

            fragment.append(self.next())

        if fragment:
            yield CodeFragment(is_macro, fragment)

    def parse(self):
        while (current := self.peek()) and current.type != ENDMARKER:
            # track current indentation
            if current.type == INDENT:
                self.indent += 1
                yield CodeFragment(False, [self.next()])
            elif current.type == DEDENT:
                self.indent -= 1
                yield CodeFragment(False, [self.next()])
            elif self.indent == 0 and (code := self.parse_import()):
                # macro import or object-like macro
                yield from code
            elif fnc := self.parse_function():
                if self.indent != 0 and fnc.is_macro:
                    # function-like macro only allowed at module scope
                    # TODO fail
                    fnc.is_macro = False
                yield fnc
            elif statement := self.parse_macro_statement():
                yield statement
            else:
                # ensure next iteration starts on a new line
                tokens = list(self.parse_line())
                yield from tokens


def transform(source: str, source_path: Optional[Path] = None, macro_only: bool = False):
    macro_code = []
    code = []
    tokens = TokenStream(tokenize(source))
    parser = Parser(tokens)
    interpreter = Interpreter()
    if source_path:
        interpreter.setup_imports(source_path)

    for node in parser.parse():
        if isinstance(node, Fragment) and node.is_macro:
            fragment = node.evaluate(interpreter)
            interpreter.exec(fragment)
            macro_code.extend(fragment)
            continue

        if macro_only:
            continue
        evaluated = list(node.evaluate(interpreter))
        code.extend(evaluated)

    if code and code[0].type == 62:
        code = code[2:]

    return macro_code, code


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


def main():
    import argparse
    args_parser = argparse.ArgumentParser("magic_macro")
    args_parser.add_argument("source")
    args_parser.add_argument("--syntax-only", action="store_true")
    args_parser.add_argument("--preprocessor", action="store_true")
    args_parser.add_argument("--run", action="store_true")

    args = args_parser.parse_args()
    source = Path(args.source)
    raw_source = source.read_text(encoding='utf-8')

    if args.syntax_only:
        tokens = TokenStream(tokenize(raw_source))
        print_syntax(tokens)
        return

    if args.preprocessor:
        macro_code, _ = transform(raw_source, source_path=source, macro_only=True)
        print(untokenize(macro_code))
    elif args.run:
        _, code = transform(raw_source, source_path=source)
        exec(untokenize(code))
    else:
        _, code = transform(raw_source, source_path=source)
        print(untokenize(code))


if __name__ == "__main__":
    main()
