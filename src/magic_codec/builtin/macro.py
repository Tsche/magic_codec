# pylint: disable=eval-used,exec-used

import ast as _ast
from dataclasses import dataclass
from token import DEDENT, ENDMARKER, INDENT, NAME, NEWLINE, NL, NUMBER, OP, STRING
from tokenize import untokenize
from typing import Any, Generator, Optional

from magic_codec.util import Cancellation, Code, ParseError, Token, TokenStream, force_conversion, get_tokens


def macro(fnc):
    """ This decorator does nothing. It is only used to flag functions and classes as macros. """
    return fnc


class _Code(Code):
    """ Tag type to mark code objects coming from the preprocessor """


class UnresolvedSymbol(Exception): 
    """ Raised when a symbol cannot be resolved in the context of the preprocessor. """


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


MACRO_PREFIX = "__macro__"

class MacroProcessor:
    __default_globals = {
        # 'tokenize': tokenize,
        # 'ast': _ast,
        'Code': Code,
        'MacroDecorator': MacroDecorator,
        'NodeTransformer': NodeTransformer,
        'macro': macro,
        'get_tokens': get_tokens
    }

    def __init__(self):
        self.globals: dict[str, Any] = self.__default_globals
        self.locals: dict[str, Any] = {}

    def resolve_symbol(self, name: str, expand=True):
        if expand and not name.startswith(MACRO_PREFIX):
            name = MACRO_PREFIX + name
        try:
            return self.locals.get(name, self.globals[name])
        except KeyError as exc:
            raise UnresolvedSymbol(f"Cannot find {name}") from exc

    def exec(self, code: str, locals: Optional[dict[str, Any]] = None):
        exec(code, self.globals, locals or self.locals)

    def eval(self, code: str, locals: Optional[dict[str, Any]] = None):
        return eval(code, self.globals, locals or self.locals)

    def reset(self):
        self.globals = self.__default_globals
        self.locals = {}

    def apply_macros(self, code: list[Token], macros: list[list[Token]]):
        call = synthesize_call_chain(macros, args=[Token(NAME, "__magic_macro_code_object")], convert_to="_Code")
        call_locals = {**self.locals,
                       '__magic_macro_code_object': code,
                       '_Code': _Code}

        # do the actual transformation
        # TODO force constants to be replaced after applying proc macros
        return self.eval(untokenize(call), call_locals).tokens

    def replace_constant(self, token: Token):
        value = self.locals[token.string]
        yield from synthesize_constant(value)

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

    def is_macro_introducer(self):
        assert self.named_expression
        return self.named_expression[0] == (NAME, "macro")
    
    def is_macro(self, context: MacroProcessor):
        assert self.named_expression
        name = parse_name(TokenStream(self.named_expression))
        return name in context.locals


class FunctionDefinition:
    def __init__(self, name: str, decorators: list[Decorator], code: list[Token], macro=False):
        self.name = name
        self.decorators = decorators
        self.code = code
        self.is_macro = macro
        self.macro_settings: list[Token] = []

    def eval(self, context: MacroProcessor):
        # evaluate macros in code
        # apply macro decorators
        self.macro_settings = []
        decorators: list[Token] = []
        macro_decorators: list[list[Token]] = []

        for decorator in self.decorators:
            if decorator.is_macro_introducer():
                if self.macro_settings:
                    raise ParseError("@macro can only be used once per function/class")
                self.is_macro = True
                self.macro_settings = decorator.named_expression

            elif decorator.is_macro(context):
                macro_decorators.append(decorator.named_expression)
            else:
                decorators.extend(decorator.to_tokens())

        code: list[Token] = [*decorators, *self.code]
        code = context.apply_macros(code, macro_decorators)
        yield from code

def parse_block(tokens: TokenStream):
    current = tokens.peek()
    if current and current.type not in (NL, NEWLINE):
        # simple statement(s) following head - parse until next line, ie:
        # def foo(): ...
        # def foo(): x=2;y=3;return x*y;
        return tokens.consume_line()
    return tokens.consume_balanced((INDENT, ...), (DEDENT, ...))

def parse_name(tokens: TokenStream, with_bang=True) -> str:
    name = tokens.expect((NAME, ...))

    if with_bang and tokens.peek() == (OP, '!'):
        tokens.next()
        # transform name directly
        return f"{MACRO_PREFIX}{name.string}"
    return name.string

def parse_import(tokens: TokenStream):
    first_token = tokens.expect((NAME, ["import", "from"]))
    return [first_token, *tokens.consume_line()]

def parse_definition(tokens: TokenStream, macro: bool=False):
    name = tokens.expect((NAME, ...))
    if macro:
        tokens.expect((OP, '!'))
        name = (NAME, f"{MACRO_PREFIX}{name.string}")
    op = tokens.expect((OP, '='))

    return [name, op, *tokens.consume_line()]

def parse_decorator(tokens: TokenStream):
    tokens.expect((OP, '@'))
    named_expression = tokens.consume_line(with_newline=False)
    if not named_expression:
        raise ParseError("named_expression expected after `@`")

    return Decorator(named_expression)

def parse_decorators(tokens: TokenStream):
    decorators = []
    while (decorator := tokens.attempt(parse_decorator)):
        decorators.append(decorator)
    return decorators

def parse_function(tokens: TokenStream):
    decorators = parse_decorators(tokens)

    code = []
    is_macro = any(decorator.is_macro_introducer() for decorator in decorators)

    while (next_token := tokens.next()):
        if next_token.type != NAME:
            raise Cancellation
            # raise ParseError(f"Unexpected token type {next_token.type}", tokens.error_context())
        if next_token.string == 'macro':
            is_macro = True
        elif next_token.string == 'async':
            code.append(next_token)
        else:
            break

    if next_token != (NAME, ["class", "def"]):
        raise Cancellation
    code.append(next_token)

    name = parse_name(tokens)
    if name.startswith(MACRO_PREFIX):
        is_macro = True
    code.append(Token(NAME, name))

    code.extend(tokens.consume_until((OP, ':')))
    code.extend(parse_block(tokens))

    return FunctionDefinition(name, decorators, code, macro=is_macro)

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

def parse_macro(tokens: TokenStream, context):
    with tokens.alt:
        return parse_definition(tokens, macro=True)

    with tokens.alt:
        tokens.expect((NAME, "macro"))
        with tokens.alt:
            return parse_definition(tokens)
        
        with tokens.alt:
            return parse_import(tokens)

        with tokens.alt:
            code = parse_function(tokens)
            code.is_macro = True
            return code.eval(context)

    return None

def transform(tokens: TokenStream):
    context = MacroProcessor()
    while (current := tokens.peek()):
        if current == ([NL, NEWLINE], ...):
            # consume newlines
            yield tokens.next()
            yield from tokens.consume_while(([NL, NEWLINE], ...))
            if code := parse_macro(tokens, context):
                context.exec(untokenize(code), context.locals)
                tokens.cursor -= 1
                continue

            with tokens.alt:
                fnc = parse_function(tokens)
                if fnc.is_macro:
                    context.exec(untokenize(fnc.eval(context)), context.locals)
                else:
                    yield from fnc.eval(context)
                tokens.cursor -= 1
                continue

            with tokens.alt:
                current = tokens.expect((NAME, ["import!", "from!"]))
                code = [(NAME, current.string[:-1]), *tokens.consume_line()]
                context.exec(untokenize(code))
                tokens.cursor -= 1
                continue

        elif current.type == NAME:
            with tokens.alt:
                name = parse_name(tokens)
                if name not in context.locals:
                    raise Cancellation

                if tokens.peek() == (OP, '('):
                    # function-like macro call
                    args = tokens.consume_balanced((OP, '('), (OP, ')'))

                    call = [(NAME, name), *args]
                    result = context.eval(untokenize(call), context.locals)
                    yield from synthesize_constant(result)
                    continue
                else:
                    # constant
                    yield from synthesize_constant(context.locals[name])
                    continue

        elif current.type == ENDMARKER:
            break

        yield tokens.next()
    yield Token(ENDMARKER, '')

# @cache
def preprocess(data: str):
    tokens    = TokenStream(Code(data).tokens)
    new_code  = Code(list(transform(tokens)))
    return new_code.string
