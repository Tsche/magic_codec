
from collections import namedtuple
from io import StringIO
from tokenize import TokenInfo, generate_tokens, untokenize
import ast
from types import NoneType
from typing import Iterable, Self

from magic_codec.macro.macro_ast import parse_string, unparse
from pegen.tokenizer import Tokenizer

class Token(namedtuple("Token", ["type", "string"])):
    type: int
    string: str

    _sloc: tuple[tuple[int, int], tuple[int, int], str] | None

    @property
    def start(self):
        if not self._sloc:
            return (0, 0)
    
    @property
    def end(self):
        if not self._sloc:
            return (0, 1)
    
    @property
    def line(self):
        if not self._sloc:
            return ""

    def __new__(cls, other: int | Self | tuple | TokenInfo, string: str = ""):
        type_: int
        string_: str
        sloc: tuple[tuple[int, int], tuple[int, int], str] | None = None

        if isinstance(other, int):
            type_ = other
            string_ = string
        elif isinstance(other, tuple) and len(other) == 2:
            type_ = int(other[0])
            string_ = str(other[1])
        elif isinstance(other,  TokenInfo):
            type_ = other.type
            string_ = other.string
            sloc = other.start, other.end, other.line
        elif isinstance(other,  Token):
            type_ = other.type
            string_ = other.string
            sloc = other._sloc
        else:
            raise TypeError(f"Cannot construct a Token object from {type(other)}{f', {string}' if string else ''}")
        
        obj = super().__new__(cls, type_, string_)
        obj._sloc = sloc
        return obj

class Code:
    __current_state: str | list[Token] | ast.AST

    def __init__(self, state: Self | str | Iterable[TokenInfo | tuple[int, str]] | ast.AST | None):
        if isinstance(state, Code):
            self.__current_state = state.__current_state
        elif isinstance(state, (int, float, bool)):
            # allow turning literal into code
            self.__current_state = repr(state)
        elif isinstance(state, type(...)):
            # allow turning literal into code
            self.__current_state = "..."
        elif isinstance(state, str):
            self.__current_state = state
        elif isinstance(state, ast.AST):
            self.__current_state = state
        elif isinstance(state, NoneType):
            self.__current_state = []
        elif isinstance(state, (Token, TokenInfo, tuple)):
            self.__current_state = [Token(state)]
        elif isinstance(state, Iterable):
            self.__current_state = []
            for token in state:
                if isinstance(token, (Token, TokenInfo, tuple)):
                    self.__current_state.append(Token(token))
                elif isinstance(token, NoneType):
                    continue
                elif isinstance(token, str):
                    self.__current_state.extend(Code(token).tokens)
                elif isinstance(token, ast.AST):
                    self.__current_state.extend(Code(token).tokens)
                elif isinstance(token, Code):
                    self.__current_state.extend(token.tokens)
                elif isinstance(token, Iterable):
                    self.__current_state.extend(Code(token).tokens)
                else:
                    raise TypeError(f"Cannot construct a Code object from {type(token)}")
        else:
            raise TypeError(f"Cannot construct a Code object from {type(state)}")

    @property
    def string(self):
        if isinstance(self.__current_state, str):
            return self.__current_state
        elif isinstance(self.__current_state, ast.AST):
            self.__current_state = ast.fix_missing_locations(self.__current_state)
            return unparse(self.__current_state)
        elif isinstance(self.__current_state, list):
            return untokenize(self.__current_state)
        raise TypeError(f"Current state has invalid type {type(self.__current_state)}")

    @property
    def ast(self):
        if isinstance(self.__current_state, ast.AST):
            return self.__current_state

        return parse_string(self.string)

    @property
    def tokens(self):
        if isinstance(self.__current_state, list):
            return self.__current_state

        code = self.string
        no_newlines = '\n' not in code
        token_list = list(generate_tokens(StringIO(self.string).readline))
        
        # remove eof marker (and possibly final newline)
        token_list = token_list[:-2 if no_newlines else -1]
        return token_list
    
    def to(self, grammar_rule: str):
        return to_ast(self, grammar_rule)

    def __repr__(self):
        return f"Code({str(self.tokens)})"
    
def to_ast(source: Code, grammar_rule: str = 'eval'):
    from magic_codec.parser.macro import MacroParser

    if not isinstance(source, Code):
        source = Code(source)
    
    # TODO make source.tokens usable directly
    with StringIO(source.string) as code:
        tokenizer = Tokenizer(generate_tokens(code.readline))
        parser = MacroParser(tokenizer)
        if grammar_rule == 'eval':
            return parser.eval().body

        return getattr(parser, grammar_rule)()