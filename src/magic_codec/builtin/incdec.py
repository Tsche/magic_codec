import keyword
import token
from typing import Generator

from magic_codec.util import TokenStream, tokenize, untokenize, Token


class UnaryExpr:
    def __init__(self, name: str, operator: str, prefix: bool):
        self.name = name
        self.operator = operator
        self.prefix = prefix

    @staticmethod
    def from_tokens(tokens: tuple[Token, Token, Token]):
        if tokens[0].type == tokens[1].type == token.OP:
            return UnaryExpr(name=tokens[2].string, operator=tokens[0].string, prefix=True)

        elif tokens[1].type == tokens[2].type == token.OP:
            return UnaryExpr(name=tokens[0].string, operator=tokens[1].string, prefix=False)

        else:
            raise TypeError("Invalid token tuple: expected the same tokenize.OP twice and a tokenize.NAME")

    def __str__(self):
        if self.prefix:
            return f"{self.operator}{self.operator}{self.name}"
        return f"{self.name}{self.operator}{self.operator}"

    def to_python(self):
        target = 0 if self.prefix else 1
        return f"(({self.name}, {self.name} := {self.name}{self.operator}1)[{target}])"

    def to_tokens(self) -> list[Token]:
        return [
            Token(token.OP, '('),
            Token(token.OP, '('),
            Token(token.NAME, self.name),
            Token(token.OP, ','),
            Token(token.NAME, self.name),
            Token(token.OP, ':='),
            Token(token.NAME, self.name),
            Token(token.OP, self.operator),
            Token(token.NUMBER, '1'),
            Token(token.OP, ')'),
            Token(token.OP, '['),
            Token(token.NUMBER, str(int(self.prefix))),
            Token(token.OP, ']'),
            Token(token.OP, ')')
        ]


def is_valid_unary_operator(token):
    return token.type == token.OP and token.string in ('+', '-')


def is_valid_name(token):
    return token.type == token.NAME and not keyword.iskeyword(token.string)


def transform(data) -> Generator[Token, None, None]:
    tokens = TokenStream(tokenize(data))

    for current in tokens:
        if is_valid_name(current):
            peek1, peek2 = tokens.peek_n(2)
            if is_valid_unary_operator(peek1) and peek1.string == peek2.string:
                yield from UnaryExpr.from_tokens((current, peek1, peek2)).to_tokens()
                tokens.next_n(2)
                continue

        elif is_valid_unary_operator(current):
            peek, name = tokens.peek_n(2)
            if peek.string == current.string and is_valid_name(name):
                yield from UnaryExpr.from_tokens((current, peek, name)).to_tokens()
                tokens.next_n(2)
                continue

        yield Token(current.type, current.string)


def preprocess(data: str):
    return untokenize(transform(data))
