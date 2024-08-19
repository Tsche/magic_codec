from io import StringIO
from pathlib import Path
import tokenize
from typing import Iterable


def assert_token_sequence(source: str, expected_tokens: list[tuple[int, str]]):
    tokens = [(token.type, token.string) for token in tokenize.generate_tokens(StringIO(source).readline)]

    assert len(tokens) == len(expected_tokens), f"Mismatched length: {len(tokens)} != {len(expected_tokens)}"
    for (actual_type, actual_value), (expected_type, expected_value) in zip(tokens, expected_tokens):
        assert actual_type == expected_type, f"Mismatched token type: {actual_type} != {expected_type}"
        assert actual_value == expected_value, f"Mismatched token value: {actual_value} != {expected_value}"


def parenthesize(tokens: Iterable[tuple[int, str]]):
    yield (tokenize.OP, '(')
    for token in tokens:
        if isinstance(token, tuple):
            yield token
        else:
            yield from token

    yield (tokenize.OP, ')')


def subscript(index: int):
    yield (tokenize.OP, '[')
    yield (tokenize.NUMBER, str(index))
    yield (tokenize.OP, ']')


def identifier(name: str):
    yield (tokenize.NAME, name)


def operator(text: str):
    yield (tokenize.OP, text)


def number(value: int):
    yield (tokenize.NUMBER, str(value))


COMMA = (tokenize.OP, ',')
PLUS = (tokenize.OP, '+')
MINUS = (tokenize.OP, '-')


def test_valid():
    assert_token_sequence(
        b"a++".decode("magic.incdec"),
        [*parenthesize([
            *parenthesize([
                identifier('a'), COMMA, identifier('a'), operator(':='), identifier('a'), PLUS, number(1)]),
            *subscript(0)]),
            (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    assert_token_sequence(
        b"a--".decode("magic.incdec"),
        [*parenthesize([
            *parenthesize([
                identifier('a'), COMMA, identifier('a'), operator(':='), identifier('a'), MINUS, number(1)]),
            *subscript(0)]),
            (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    assert_token_sequence(
        b"++a".decode("magic.incdec"),
        [*parenthesize([
            *parenthesize([
                identifier('a'), COMMA, identifier('a'), operator(':='), identifier('a'), PLUS, number(1)]),
            *subscript(1)]),
            (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    assert_token_sequence(
        b"--a".decode("magic.incdec"),
        [*parenthesize([
            *parenthesize([
                identifier('a'), COMMA, identifier('a'), operator(':='), identifier('a'), MINUS, number(1)]),
            *subscript(1)]),
            (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])


def test_invalid_strings():
    # double quote
    assert_token_sequence(
        b'"a++"'.decode("magic.incdec"),
        [(tokenize.STRING, '"a++"'), (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    assert_token_sequence(
        b'"a--"'.decode("magic.incdec"),
        [(tokenize.STRING, '"a--"'), (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    assert_token_sequence(
        b'"++a"'.decode("magic.incdec"),
        [(tokenize.STRING, '"++a"'), (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    assert_token_sequence(
        b'"--a"'.decode("magic.incdec"),
        [(tokenize.STRING, '"--a"'), (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    # single quote
    assert_token_sequence(
        b"'a++'".decode("magic.incdec"),
        [(tokenize.STRING, "'a++'"), (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    assert_token_sequence(
        b"'a--'".decode("magic.incdec"),
        [(tokenize.STRING, "'a--'"), (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    assert_token_sequence(
        b"'++a'".decode("magic.incdec"),
        [(tokenize.STRING, "'++a'"), (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])

    assert_token_sequence(
        b"'--a'".decode("magic.incdec"),
        [(tokenize.STRING, "'--a'"), (tokenize.NEWLINE, ''), (tokenize.ENDMARKER, '')])


def test_can_run():
    source = Path(__file__).parent / "incdec.py"
    processed_source = source.read_text(encoding="magic.incdec")
    exec(processed_source)


if __name__ == "__main__":
    test_valid()
    test_invalid_strings()
    test_can_run()