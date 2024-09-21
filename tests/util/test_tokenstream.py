from token import NAME, OP
from magic_codec.util import Token, TokenStream, tokenize


def test_consume_balanced():
    tokens = TokenStream(tokenize("foo(x(y(z))) + 2"))
    consumed = tokens.consume_balanced((OP, '('), (OP, ')'))
    expected = [Token(NAME, 'foo'), Token(OP, '('), Token(NAME, 'x'), Token(OP, '('), Token(NAME, 'y'),
                Token(OP, '('), Token(NAME, 'z'), Token(OP, ')'), Token(OP, ')'), Token(OP, ')')]
    assert consumed == expected
