# pylint: disable=eval-used,exec-used

import ast as _ast
from io import StringIO
from token import DEDENT, ENDMARKER, INDENT, NAME, NEWLINE, NL, NUMBER, OP, STRING
from tokenize import generate_tokens, untokenize
from types import EllipsisType
from typing import Any, Optional

from magic_codec.util import Code, Token, get_tokens


def macro(fnc):
    """ This decorator does nothing. It is only used to flag functions and classes as macros. """
    return fnc


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


def consume_line(tokens: list[Token]):
    consumed = []
    for token in tokens:
        consumed.append(token)
        if token.type in (NEWLINE, NL,  ENDMARKER):
            break
    return consumed


TokenQuery = tuple[int | EllipsisType, str | EllipsisType]


def consume_match(tokens: list[Token], increase: TokenQuery, decrease: TokenQuery):
    consumed = []
    level = 0

    def compare(token, needle):
        type_, string = needle
        return (type_ is ... or type_ == token.type) and (string is ... or string == token.string)

    for token in tokens:
        consumed.append(token)
        if compare(token, increase):
            level += 1
        elif compare(token, decrease):
            level -= 1

            if level == 0:
                break
    return consumed


def parse_name(tokens: list[Token]):
    name = []
    for token in tokens:
        if token.type != NAME and token != (OP, '.'):
            break
        name.append(token)
    return name


def parse_decorators(tokens: list[Token]):
    idx = 0
    decorators = []
    while tokens[idx] == (OP, '@') and idx <= len(tokens) - 2:
        name = parse_name(tokens[idx + 1:])
        if not name:
            break

        idx += len(name)
        args = []

        if tokens[idx + 1] == (OP, '('):
            args = list(consume_match(tokens[idx+1:], (OP, '('), (OP, ')')))
            idx += 1
        elif tokens[idx + 1].type in (NL, NEWLINE):
            idx += 1
        else:
            break

        decorators.append((name, args))
        idx += 1 + len(args)

    if tokens[idx].type != NAME or tokens[idx].string not in ('def', 'class', 'macro'):
        return [], 0

    return decorators, idx


def synthesize_call(function: str | list[Token], expression: list[Token]):
    name = [Token(NAME, function)] if isinstance(function, str) else [*function]
    return [*name, Token(OP, '('), *expression, Token(OP, ')')]


def chain_calls(calls: list[list[Token]], args: list[Token], convert_to: Optional[str] = None):
    if not calls:
        return synthesize_call(convert_to, args) if convert_to else args
    call = synthesize_call(calls[0], chain_calls(calls[1:], args, convert_to))
    return synthesize_call(convert_to, call) if convert_to else call


def tokenize_constant(value: Any):
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


class MacroProcessor:
    def __init__(self):
        self.globals: dict[str, Any] = {
                                        # 'tokenize': tokenize,
                                        # 'ast': _ast,
                                        'Code': Code,
                                        'MacroDecorator': MacroDecorator,
                                        'NodeTransformer': NodeTransformer,
                                        'macro': macro,
                                        'get_tokens': get_tokens
                                        }
        self.locals: dict[str, Any] = {}

    def parse_macro_import(self, tokens: list[Token]):
        code = []
        for idx, token in enumerate(tokens):
            if token.type == OP and token.string == '(':
                names = consume_match(tokens[idx:], (OP, '('), (OP, ')'))
                code.extend(names)
                continue

            code.append(token)
            if token.type in (NL, NEWLINE, ENDMARKER):
                break

        exec(untokenize(code), self.globals, self.globals)
        return len(code)

    def parse_macro_constant(self, tokens: list[Token]):
        assert tokens[1] == (OP, '=')

        if (code := consume_line(tokens)):
            exec(untokenize(code), self.globals, self.locals)
        return len(code)

    def parse_macro_function(self, tokens: list[Token],
                             decorators: list[list[Token]],
                             macro_decorators: Optional[list[list[Token]]] = None):
        body = consume_match(tokens, (INDENT, ...), (DEDENT, ''))
        consumed = len(body)
        
        body = [*[token
                  for decorator in decorators
                  for token in decorator], *body]

        if not body:
            return 0

        if macro_decorators:
            call = chain_calls(macro_decorators, args=[Token(NAME, "__magic_macro_code_object")], convert_to="_Code")
            call_locals = {**self.locals,
                           '__magic_macro_code_object': body,
                           '_Code': _Code}
            transformed = eval(untokenize(call), self.globals, call_locals)
            body = transformed.tokens

        exec(untokenize(body), self.globals, self.locals)
        return consumed

    def apply_macros(self, macros: list[list[Token]], tokens: list[Token]):
        if tokens[0].type != NAME or tokens[0].string not in ('def', 'class'):
            return [], 0

        code = consume_match(tokens, (INDENT, ...), (DEDENT, ...))
        call = chain_calls(macros, args=[Token(NAME, "__magic_macro_code_object")], convert_to="_Code")
        call_locals = {**self.locals,
                       '__magic_macro_code_object': code,
                       '_Code': _Code}

        # do the actual transformation
        transformed = eval(untokenize(call), self.globals, call_locals)

        # force constants to be replaced after applying proc macros
        return self.replace_constants(transformed.tokens), len(code)

    def replace_constants(self, tokens: list[Token]):
        for token in tokens:
            if token.type == NAME and token.string in self.locals:
                yield from self.replace_constant(token)
                continue
            yield token

    def replace_constant(self, token: Token):
        value = self.locals[token.string]
        yield from tokenize_constant(value)

    def transform(self, tokens: list[Token]):
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]

            if token.type == NAME and token.string == "macro":
                idx += 1
                assert tokens[idx].type == NAME, "`macro` can only be followed by an identifier, def or class"
                next_token = tokens[idx]
                remaining_tokens = tokens[idx:]
                if next_token.string in ("def", "class"):
                    idx += self.parse_macro_function(remaining_tokens, [])
                elif next_token.string in ("import", "from"):
                    idx += self.parse_macro_import(remaining_tokens)
                elif next_token.type == NAME:
                    idx += self.parse_macro_constant(remaining_tokens)
                else:
                    # `macro` appeared in an unexpected context, yield it
                    yield token
                continue

            elif token == (OP, '@'):
                decorators, consumed = parse_decorators(tokens[idx:])
                if consumed:
                    idx += consumed
                    decorators_ = []
                    macro_decorators = []
                    is_macro = False
                    for decorator_name, decorator_args in decorators:
                        if len(decorator_name) == 1 and decorator_name[0].string == "macro":
                            is_macro = True
                            continue

                        # TODO properly look up decorators with more than one token as name
                        if len(decorator_name) > 1 or decorator_name[0].string not in self.locals:
                            # yield non-macro decorators
                            decorators_.append([Token(OP, '@'), *decorator_name, *decorator_args, Token(NEWLINE, '\n')])
                            continue
                        macro_decorators.append([*decorator_name, *decorator_args])

                    if tokens[idx] == (NAME, "macro"):
                        idx += 1
                        is_macro = True

                    if is_macro:
                        idx += self.parse_macro_function(tokens[idx:], decorators_, macro_decorators)
                        continue

                    yield from decorators_
                    if macro_decorators:
                        new_tokens, consumed = self.apply_macros(macro_decorators, tokens[idx:])
                        idx += consumed
                        yield from new_tokens

                    continue

            elif token.type == NAME and token.string in self.locals:
                idx += 1
                if tokens[idx].type == OP and tokens[idx].string == '(':
                    # function-like macro call
                    args = consume_match(tokens[idx:], (OP, '('), (OP, ')'))
                    idx += len(args)

                    call = [token, *args]
                    result = eval(untokenize(call), self.globals, self.locals)
                    yield from tokenize_constant(result)
                else:
                    # constant
                    yield from self.replace_constant(token)
                continue

            elif token.type == NAME and token.string in ("def", "class"):
                name_token = tokens[idx + 1]
                macro_token = tokens[idx + 2]

                if macro_token == (OP, '!'):
                    print("MACRO FUNCTION")
                    idx += 3
                    continue

            idx += 1
            yield token.type, token.string


# @cache
def preprocess(data: str):
    tokens = generate_tokens(StringIO("\n" + data).readline)
    processor = MacroProcessor()
    new_tokens = processor.transform([Token(token.type, token.string) for token in tokens])
    new_source = untokenize(new_tokens)
    return new_source
