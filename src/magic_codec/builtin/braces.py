from io import StringIO
from tokenize import TokenInfo, generate_tokens, untokenize
import tokenize
from typing import Generator, Iterable


def preprocess_tokens(tokens: Iterable[TokenInfo]) -> Generator[TokenInfo | tuple[int, str], None, None]:
    indent = 0
    tokens = list(tokens)
    for (idx, token) in enumerate(tokens):
        if token.type in (tokenize.INDENT, tokenize.DEDENT):
            continue

        if token.type == tokenize.OP:

            # Since Python uses curly braces for dictionaries, it is not advisable to
            # simply drop all of those and treat them as indentation modifiers.

            # Instead we only count curly braces as indentation modifiers if and only if:
            # - '{' is followed by a newline
            # - '}' is preceeded by a newline

            if token.string == '{':
                assert idx < len(tokens) - 1
                if tokens[idx + 1].type in (tokenize.NL, tokenize.NEWLINE):
                    yield tokenize.COLON
                    indent += 1
                    continue

            elif token.string == '}':
                assert idx != 0
                if tokens[idx - 1].type in (tokenize.NL, tokenize.NEWLINE):
                    indent -= 1
                    continue

        elif token.type in (tokenize.NL, tokenize.NEWLINE):
            yield token
            yield tokenize.INDENT, '    '*indent
            continue

        yield token


EXACT_TOKENS = {type_: value for value, type_ in tokenize.EXACT_TOKEN_TYPES.items()}


def cleanup(tokens: Iterable[TokenInfo | tuple[int, str] | int]):
    for token in tokens:
        if isinstance(token, int):
            assert token in EXACT_TOKENS, f"Invalid token type {token}"
            yield tokenize.OP, EXACT_TOKENS[token]
        else:
            yield token


def preprocess(data: str):
    tokens = list(generate_tokens(StringIO(data).readline))
    processed = preprocess_tokens(tokens)
    return untokenize(cleanup(processed))
