import pytest
import re

from magic_codec.util import Token

# Assuming Token class code is here

@pytest.fixture
def token():
    return Token(type=1, string="hello")


@pytest.mark.parametrize("query, expected", [
    ((1, "hello"), True),                     # Exact match
    ((1, "world"), False),                    # String mismatch
    ((2, "hello"), False),                    # Type mismatch

    ((1, re.compile(r"^h.*o$")), True),       # Regex match
    ((1, re.compile(r"^foo$")), False),       # Regex no match

    ((1, ["hello", "world"]), True),          # List of possible strings (match)
    ((1, ["foo", "bar"]), False),             # List of possible strings (no match)
    (([1, 2], "hello"), True),                # List of possible types (match)
    (([2, 3], "hello"), False),               # List of possible types (no match)

    ((lambda x: x == 1, "hello"), True),      # Callable type query (match)
    ((lambda x: x == 2, "hello"), False),     # Callable type query (no match)
    ((1, lambda x: x == "hello"), True),      # Callable string query (match)
    ((1, lambda x: x == "world"), False),     # Callable string query (no match)

    ((1, ...), True),                         # Wildcard string
    ((2, ...), False),                        # Wildcard string, type mismatch
    ((..., "hello"), True),                   # Wildcard type
    ((..., "world"), False),                  # Wildcard type, string mismatch
    ((..., ["hello", "world"]), True),        # Wildcard type, list of possible strings (match)
    ((..., ["foo", "bar"]), False),           # Wildcard type, list of possible strings (no match)
    ((..., re.compile(r"^h")), True),         # Wildcard type, regex (match)
    ((..., re.compile(r"^x")), False),        # Wildcard type, regex (no match)
    ((..., lambda x: x == "hello"), True),    # Wildcard type with callable string query (match)
    ((..., lambda x: x == "world"), False),   # Wildcard type with callable string query (no match)
    (([1, 2], ...), True),                    # List of possible types, wildcard string (match)
    (([5, 9], ...), False),                   # List of possible types, wildcard string (no match)
    ((lambda x: x == 1, ...), True),          # Callable type query with wildcard string (match)
    ((lambda x: x == 2, ...), False),         # Callable type query with wildcard string (no match)
    ((..., ...), True)                        # Wildcard type, wildcard string
])
def test_token_eq(token, query, expected):
    assert (token == query) == expected


def test_invalid_type_query(token):
    with pytest.raises(TypeError):
        token == (3.14, "hello")  # Invalid type query type


def test_invalid_string_query(token):
    with pytest.raises(TypeError):
        token == (1, 12345)  # Invalid string query type
