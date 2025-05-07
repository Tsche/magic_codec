# import pytest
# from magic_codec.builtin.macro import parse_name

# from magic_codec.util import TokenStream, tokenize
# from token import NAME

# def tokens_of(code: str):
#     return TokenStream(tokenize(code))


# @pytest.mark.parametrize("name", ["foo", "foo!"])
# def test_transform_name(name):
#     tokens = parse_name(tokens_of(name), with_bang=True)
#     assert tokens == name

# @pytest.mark.parametrize("line", [
#     "foo\nbar\n", 
#     "foo(\noof,\nfoo)\nbar",
#     "foo(\noof,\nfoo(oof\n))\nbar",
#     "foo[\noof,\nfoo]\nbar",
#     "foo{\noof,\nfoo}\nbar",
#     "foo(\noof[\nfoo\n{bar\nbaz[foo\n(\nf\n)([{}])]}],\nfoo)\nbar",
# ])
# def test_consume_line(line):
#     tokens = tokens_of(line)
#     first_line = tokens.consume_line()
#     assert first_line
#     assert tokens.peek() == (NAME, "bar")