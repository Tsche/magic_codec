import pytest
from magic_codec.builtin.macro import Context, parse_decorators, parse_function
from magic_codec.util import TokenStream, tokenize
from tokenize import untokenize
def test_decorator_simple():
  code = "@test\n"
  tokens = TokenStream(tokenize(code))
  decorators = parse_decorators(tokens)
  assert decorators

def test_function():
  code = "@foo\nmacro async def foo(bar) -> int:\n    print('hi')\n"
  tokens = TokenStream(tokenize(code))
  fnc = parse_function(tokens)
  assert fnc
  assert fnc.is_macro

if __name__ == "__main__":
  test_function()