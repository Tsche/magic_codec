# pylint: disable=eval-used,exec-used

import ast as _ast
from io import StringIO
from token import DEDENT, ENDMARKER, INDENT, NAME, NEWLINE, NL, NUMBER, OP, STRING
from tokenize import generate_tokens, untokenize
from types import EllipsisType
from typing import Any, Optional

from magic_codec.util import Code, ParseError, Token, TokenStream, force_conversion, get_tokens


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


MACRO_PREFIX = "___magic_macro___"

def parse_name(tokens: TokenStream):
    current = tokens.peek()
    if current.type != NAME:
        return None
    tokens.commit()

    if tokens.peek() == (OP, '!'):
        tokens.commit()
        return MACRO_PREFIX + current.string
    tokens.revert()
    return current.string

def parse_dotted_name(tokens: TokenStream, with_bang=False):
    name = []
    while (segment := parse_name(tokens)):
        name.append(segment)
        if tokens.peek() != (OP, '.'):
            tokens.revert()

    return name


def parse_block(tokens: TokenStream):
    if tokens.peek().type not in (NL, NEWLINE):
        # simple statement(s) following head - parse until next line, ie:
        # def foo(): ...
        # def foo(): x=2;y=3;return x*y;
        return tokens.consume_line()
    return tokens.consume_balanced((INDENT, ...), (DEDENT, ...))


def parse_decorators(tokens: TokenStream):
    decorators = []
    for current in tokens:
        if current != (OP, '@'):
            # unexpected token, stop
            break
        
        # TODO iter until next NL from here
        current_decorator = parse_dotted_name(tokens)
        if not current_decorator:
            break

        if tokens.peek() == (OP, '('):
            arg_list = tokens.consume_balanced((OP, '('), (OP, ')'), 1)
            # TODO: decorators like @foo().bar().baz() might exist
            current_decorator.append(arg_list)
        
        decorators.append(current_decorator)
    return decorators

def synthesize_call(function: str | list[Token], expression: list[Token]):
    name = [Token(NAME, function)] if isinstance(function, str) else [*function]
    return [*name, Token(OP, '('), *expression, Token(OP, ')')]


def chain_calls(calls: list[list[Token]], args: list[Token], convert_to: Optional[str] = None):
    if not calls:
        return synthesize_call(convert_to, args) if convert_to else args
    call = synthesize_call(calls[0], chain_calls(calls[1:], args, convert_to))
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


class Definition:
    def __init__(self, name, body) -> None:
        self.name = name
        self.body = body
    
    def __iter__(self):
        return self

    def __next__(self):
        yield from self.name
        yield (OP, '=')
        yield from self.body


class ClassDefinition(Definition):
    def __init__(self, name, body, bases, generics=None) -> None:
        super().__init__(name, body)
        self.name = name
        self.bases = bases
        self.generics = generics

    def __iter__(self):
        return self

    def __next__(self):
        yield NAME, "class"
        yield self.name
        if self.generics:
            yield from self.generics

        if self.bases:
            yield from self.bases


class FunctionDefinition(Definition):
    def __init__(self, name, body, params, generics=None, return_type=None) -> None:
        super().__init__(name, body)
        self.params = params
        self.generics = generics
        self.return_type = return_type

    def __iter__(self):
        return self
    
    def __next__(self):
        yield NAME, "def"
        yield self.name
        if self.generics:
            yield from self.generics
        yield from self.params
        if self.return_type:
            yield from self.return_type

def parse_function_or_class_head(tokens: TokenStream):
    is_macro, is_async, is_class = False, False, False
    while (next_token := tokens.peek()):
        if next_token.type != NAME:
            raise ParseError("Unexpected token type {next_token.type}", tokens.error_context())
        match next_token.string:
            case 'macro':
                is_macro = True
            case 'async':
                is_async = True
            case 'class':
                is_class = True
            case 'def':
                pass

    assert kind == (NAME, "def", "class")

    name = tokens.next()
    assert name.type == NAME

    # TODO parameterized generics
    next_token = tokens.peek()
    generics = None
    if next_token == (OP, '['):
        generics = tokens.consume_balanced((OP, '['), (OP, ']'))
        next_token = tokens.peek()

    assert next_token == (OP, '(')
    param_list = tokens.consume_balanced((OP, '('), (OP, ')'))
    assert param_list

    if kind.string == 'def':
        return_type = None
        if tokens.peek() == (OP, '->'):
            # trailing type annotation
            return_type = tokens.consume_until((OP, ':'))
            body = parse_block(tokens)
            return FunctionDefinition(name, body, generics=generics, params=param_list, return_type=return_type)
    body = parse_block(tokens)
    return ClassDefinition(name, body, generics=generics, bases=param_list)


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
        eval(code, self.globals, locals or self.locals)

    def reset(self):
        self.globals = self.__default_globals
        self.locals = {}

    def parse_macro_import(self, tokens: TokenStream):
        # TODO from ... import foo
        # parsed as name ellipsis name name

        code = []
        for token in tokens:
            code.append(token)
            if tokens.peek() == (OP, '('):
                names = tokens.consume_balanced((OP, '('), (OP, ')'))
                code.extend(names)
                break

            if token.type in (NL, NEWLINE, ENDMARKER):
                break

        return untokenize(code)

    def parse_macro_constant(self, tokens: TokenStream):
        assert tokens.peek() == (NAME, ...)
        assert tokens.peek() == (OP, '=')

        if (code := tokens.consume_line()):
            return untokenize(code)

    def parse_macro_function(self, tokens: TokenStream,
                             decorators: Optional[list[list[Token]]] = None,
                             macro_decorators: Optional[list[list[Token]]] = None):
        kind = tokens.next()
        assert kind == (NAME, ["def", "class"])
        name = parse_dotted_name(tokens)
        body = [kind, *name]
        body.extend(tokens.consume_balanced((INDENT, ...), (DEDENT, '')))

        body = [*[token
                  for decorator in decorators or []
                  for token in decorator], *body]

        # TODO always apply macro decorator to wrap macros in some identifiable type
        # alternatively store macros only with special name
        # this is needed to import macros from other modules
        # => otherwise macro decorators and regular decorators become ambiguous without bang-names
        if macro_decorators:
            body = self.apply_macros(body, macro_decorators)

        return untokenize(body)

    def apply_macros(self, code: list[Token], macros: list[list[Token]]):
        call = chain_calls(macros, args=[Token(NAME, "__magic_macro_code_object")], convert_to="_Code")
        call_locals = {**self.locals,
                       '__magic_macro_code_object': code,
                       '_Code': _Code}

        # do the actual transformation
        # TODO force constants to be replaced after applying proc macros
        return self.eval(untokenize(call), call_locals)

    def replace_constants(self, tokens: list[Token]):
        for token in tokens:
            if token.type == NAME and token.string in self.locals:
                yield from self.replace_constant(token)
                continue
            yield token

    def replace_constant(self, token: Token):
        value = self.locals[token.string]
        yield from synthesize_constant(value)

    def transform(self, tokens: TokenStream):
        # holding globals and locals in the MacroProcessor object while having this
        # function accept tokens as argument instead allows incremental transformation

        for token in tokens:
            with tokens.rollback as lookahead:
                if token.type in (NL, NEWLINE):
                    next_token = lookahead.next()
                    # `@` on a new line can only mean we found a decorator
                    assert next_token == (OP, '@')

                    decorators = parse_decorators(lookahead)
                    assert decorators

                    next_token = lookahead.next()
                    if next_token == (NAME, "macro"):
                        # ie `macro def foo()` or `macro class Bar`
                        is_macro = True
                        next_token = lookahead.next()

                    # make extra sure that we found decorators for a function or a class and not matrix multiplication
                    assert next_token == (NAME, ["def", "class"])
                    # done parsing the decorators - commit progress thus far
                    lookahead.commit(upstream=True)

                    regular_decorators = []
                    macro_decorators = []
                    is_macro = False
                    for decorator_name, decorator_args in decorators:
                        if len(decorator_name) == 1 and decorator_name[0].string == "macro":
                            is_macro = True
                            continue

                        # TODO properly look up decorators with more than one token as name
                        if len(decorator_name) > 1 or decorator_name[0].string not in self.locals:
                            regular_decorators.append([Token(OP, '@'), *decorator_name, *decorator_args, Token(NEWLINE, '\n')])
                            continue
                        macro_decorators.append([*decorator_name, *decorator_args])

                    if is_macro:
                        self.parse_macro_function(lookahead, regular_decorators, macro_decorators)
                    else:
                        yield from regular_decorators
                        if macro_decorators:
                            yield from self.apply_macros(macro_decorators, lookahead)

                    continue

                elif token == (NAME, "macro"):
                    next_token = lookahead.peek()
                    # the contextual keyword `macro` can only appear before another identifier
                    assert next_token.type == NAME
                    lookahead.revert()

                    if next_token.string in ("import", "from"):
                        code = self.parse_macro_import(lookahead)
                    elif next_token.string in ("def", "class"):
                        code = self.parse_macro_function(lookahead, [])
                    else:
                        code = self.parse_macro_constant(lookahead)

                    self.exec(code)
                    continue

                elif token == (NAME, ["def", "class"]):
                    next_token = lookahead.peek()
                    assert next_token == (NAME, ...)
                    assert lookahead.peek() == (OP, '!')
                    assert lookahead.peek() == (OP, ['(', ':'])

                    self.parse_macro_function(lookahead, [])
                    continue

                elif token.type == NAME and token.string in self.locals:
                    next_token = lookahead.peek()
                    if next_token == (OP, '('):
                        # function-like macro call
                        args = lookahead.consume_balanced((OP, '('), (OP, ')'))

                        call = [token, *args]
                        result = eval(untokenize(call), self.globals, self.locals)
                        yield from synthesize_constant(result)
                    elif next_token == (OP, '!'):
                        next_token = lookahead.next()
                        # macro bangs can only be parsed as
                        # - function name -> next token is (
                        # - class name    -> next token is ( or :
                        # - decorator     -> next token is ( or a newline
                        #
                        # At this point the only expected possibility is a macro bang being used in
                        # a call expression.
                        assert next_token.type == (OP, '(')
                        # TODO
                    else:
                        # constant
                        yield from self.replace_constant(token)
                    continue
                # TODO macro! definitions

            yield token.type, token.string
        yield ENDMARKER, ''


# @cache
def preprocess(data: str):
    tokens    = TokenStream(Code(data).tokens)
    processor = MacroProcessor()
    new_code  = Code(processor.transform(tokens))
    return new_code.string
