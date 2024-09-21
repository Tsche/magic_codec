import pytest
from magic_codec.builtin.macro import parse_name

from magic_codec.util import TokenStream, tokenize


def tokens_of(code: str):
    return TokenStream(tokenize(code))


@pytest.mark.parametrize("code, expected", [
    ("foo", "foo"),
    ("foo.bar", "foo.bar"),
    ("foo!", "___magic_macro___foo"),
    ("foo!.bar", "___magic_macro___foo.bar")
])
def test_transform_name(code, expected):
    tokens = parse_name(tokens_of(code), with_bang=True)
    assert tokens == list(tokenize(expected))[:-1]
