import pytest
from magic_codec.builtin.macro import MacroProcessor

from magic_codec.util import TokenStream, get_tokens

@pytest.fixture
def processor():
    return MacroProcessor()


def tokens_of(code: str):
    return TokenStream(get_tokens(code))


@pytest.mark.parametrize("fnc, test", [
    (MacroProcessor.parse_macro_constant, "var = 2"),

    (MacroProcessor.parse_macro_import, "import traceback"),
    (MacroProcessor.parse_macro_import, "from functools import cache"),
    (MacroProcessor.parse_macro_import, """from token import (DEDENT, ENDMARKER,
INDENT, NAME, NEWLINE, NL, NUMBER, OP, STRING)"""),

    (MacroProcessor.parse_macro_function, """\
def foo(bar: str):
    print("zoinks")
    if test:
        boings()
"""),
    (MacroProcessor.parse_macro_function, "def foo(bar: str): ...")
])
def test_roundtrip(processor: MacroProcessor, fnc, test: str):
    code = fnc(processor, tokens_of(test))
    print(code)
    assert get_tokens(code) == get_tokens(test)