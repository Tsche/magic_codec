from io import StringIO
from tokenize import generate_tokens, untokenize
import tokenize


def transform(data: str):
    tokens = list(generate_tokens(StringIO(data).readline))
    indent = 0

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
                    yield (tokenize.OP, ':')
                    indent += 1
                    continue

            elif token.string == '}':
                assert idx != 0
                if tokens[idx - 1].type in (tokenize.NL, tokenize.NEWLINE):
                    indent -= 1
                    continue

        elif token.type in (tokenize.NL, tokenize.NEWLINE):
            yield (token.type, token.string)
            yield (tokenize.INDENT, '    '*indent)
            continue

        yield (token.type, token.string)


def preprocess(data: str):
    return untokenize(transform(data))
