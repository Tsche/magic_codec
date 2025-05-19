
from io import StringIO
from tokenize import TokenInfo, generate_tokens, untokenize
import ast
from types import NoneType
from typing import Iterable, Self

from magic_codec.macro.macro_ast import parse_string, unparse
from pegen.tokenizer import Tokenizer

class Code:
    __current_state: str | list[TokenInfo] | list[tuple[int, str]] | ast.AST

    def __init__(self, state: Self | str | Iterable[TokenInfo | tuple[int, str]] | ast.AST | None):
        if isinstance(state, Code):
            self.__current_state = state.__current_state
        elif isinstance(state, (TokenInfo, tuple)):
            self.__current_state = [state]
        elif isinstance(state, NoneType):
            self.__current_state = []
        elif isinstance(state, str):
            self.__current_state = state
        elif isinstance(state, Iterable):
            self.__current_state = [(int(token.type), str(token.string)) if isinstance(token, TokenInfo) else (int(token[0]), str(token[1])) 
                                    for token in state]
        elif isinstance(state, ast.AST):
            self.__current_state = state
        else:
            raise TypeError(f"Cannot construct a Code object from {type(state)}")

    @property
    def string(self):
        if isinstance(self.__current_state, str):
            return self.__current_state
        elif isinstance(self.__current_state, ast.AST):
            self.__current_state = ast.fix_missing_locations(self.__current_state)
            return unparse(self.__current_state)
        elif isinstance(self.__current_state, Iterable):
            return untokenize(self.__current_state)
        raise TypeError(f"Current state has invalid type {type(self.__current_state)}")

    @property
    def ast(self):
        if isinstance(self.__current_state, ast.AST):
            return self.__current_state

        return parse_string(self.string)

    @property
    def tokens(self):
        if isinstance(self.__current_state, Iterable) and not isinstance(self.__current_state, str):
            return list(self.__current_state)
        code = self.string
        no_newlines = '\n' not in code
        token_list = list(generate_tokens(StringIO(self.string).readline))
        if no_newlines:
            # drop final newline and eof marker
            token_list = token_list[:-2]
        return token_list
    
    def to(self, grammar_rule: str):
        return to_ast(self, grammar_rule)

    def __repr__(self):
        return f"Code({str(self.tokens)})"
    
def to_ast(source: Code, grammar_rule: str = 'eval'):
    from magic_codec.grammar.macro_parser import MacroPythonParser

    if not isinstance(source, Code):
        source = Code(source)
    
    # TODO make source.tokens usable directly
    with StringIO(source.string) as code:
        tokenizer = Tokenizer(generate_tokens(code.readline))
        parser = MacroPythonParser(tokenizer)
        if grammar_rule == 'eval':
            return parser.eval().body

        return getattr(parser, grammar_rule)()