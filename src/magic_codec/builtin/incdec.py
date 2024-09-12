from io import StringIO
import keyword
from tokenize import TokenInfo, generate_tokens
import tokenize

from magic_codec.util import TokenStream


class UnaryExpr:
    def __init__(self, name: str, operator: str, prefix: bool):
        self.name = name
        self.operator = operator
        self.prefix = prefix

    @staticmethod
    def from_tokens(tokens: tuple[TokenInfo, TokenInfo, TokenInfo]):
        if tokens[0].type == tokens[1].type == tokenize.OP:
            return UnaryExpr(name=tokens[2].string, operator=tokens[0].string, prefix=True)

        elif tokens[1].type == tokens[2].type == tokenize.OP:
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

    def to_tokens(self):
        return [
            (tokenize.OP, '('),
            (tokenize.OP, '('),
            (tokenize.NAME, self.name),
            (tokenize.OP, ','),
            (tokenize.NAME, self.name),
            (tokenize.OP, ':='),
            (tokenize.NAME, self.name),
            (tokenize.OP, self.operator),
            (tokenize.NUMBER, '1'),
            (tokenize.OP, ')'),
            (tokenize.OP, '['),
            (tokenize.NUMBER, str(int(self.prefix))),
            (tokenize.OP, ']'),
            (tokenize.OP, ')')
        ]


def is_valid_unary_operator(token):
    return token.type == tokenize.OP and token.string in ('+', '-')


def is_valid_name(token):
    return token.type == tokenize.NAME and not keyword.iskeyword(token.string)


def transform(data):
    tokens = TokenStream(generate_tokens(StringIO(data).readline))

    for current in tokens:
        if is_valid_name(current):
            peek1, peek2 = tokens.peek(2)
            if is_valid_unary_operator(peek1) and peek1.string == peek2.string:
                yield from UnaryExpr.from_tokens((current, peek1, peek2)).to_tokens()
                tokens.commit()
                continue

        elif is_valid_unary_operator(current):
            peek, name = tokens.peek(2)
            if peek.string == current.string and is_valid_name(name):
                yield from UnaryExpr.from_tokens((current, peek, name)).to_tokens()
                tokens.commit()
                continue

        yield current.type, current.string


def preprocess(data: str):
    return tokenize.untokenize(transform(data))
