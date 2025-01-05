from tokenize import INDENT, DEDENT, OP, NL, NEWLINE
from typing import Generator, Iterable
from magic_codec.util import Token, tokenize, untokenize


def preprocess_tokens(tokens: Iterable[Token]) -> Generator[Token, None, None]:
    indent = 0
    tokens = list(tokens)
    for (idx, token) in enumerate(tokens):
        if token.type in (INDENT, DEDENT):
            continue

        if token.type == OP:

            # Since Python uses curly braces for dictionaries, it is not advisable to
            # simply drop all of those and treat them as indentation modifiers.

            # Instead we only count curly braces as indentation modifiers if and only if:
            # - '{' is followed by a newline
            # - '}' is preceded by a newline

            if token.string == '{':
                assert idx < len(tokens) - 1
                if tokens[idx + 1].type in (NL, NEWLINE):
                    yield Token(OP, ':')
                    indent += 1
                    continue

            elif token.string == '}':
                assert idx != 0
                if tokens[idx - 1].type in (NL, NEWLINE):
                    indent -= 1
                    continue

        elif token.type in (NL, NEWLINE):
            yield token
            yield Token(INDENT, '    ' * indent)
            continue

        yield token


def preprocess(data: str):
    tokens = tokenize(data)
    processed = preprocess_tokens(tokens)
    return untokenize(processed)
