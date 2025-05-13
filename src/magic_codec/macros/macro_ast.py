import ast
from collections import UserList
from io import StringIO
from keyword import iskeyword, issoftkeyword
import re
import sys
from tokenize import TokenInfo, generate_tokens, tokenize, untokenize
from types import NoneType
from typing import Iterable, Self, TypeVar, Union

from pegen.tokenizer import Tokenizer

class MacroCall(ast.Call): ...

class MacroStmt(ast.stmt):
    if sys.version_info >= (3, 10):
        __match_args__ = ("expr", "body")
    _fields = ("expr", "body")
    expr: Union[ast.Name, ast.Call]
    body: list

    def __init__(self, expr: Union[ast.Name, ast.Call], body: list):
        self.expr = expr
        self.body = body

class MacroName(ast.Name):
    @property
    def string(self):
        return self.id

def maybe_macro(condition: bool, name: str):
    if condition:
        return MacroName(name)
    return name

class UnparsedFragment(UserList, ast.AST):
    if sys.version_info >= (3, 10):
        __match_args__ = ("data")

    data: list[TokenInfo]
    _fields = ("data",)

class TokenLiteral(UnparsedFragment): ...

class FunctionDef(ast.FunctionDef):
    if sys.version_info >= (3, 10):
        __match_args__ = [*ast.FunctionDef.__match_args__, 'is_macro']
    is_macro: bool
    _fields = (*ast.FunctionDef._fields, 'is_macro')

    def __init__(self, *args, is_macro: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_macro = is_macro

class AsyncFunctionDef(ast.AsyncFunctionDef):
    if sys.version_info >= (3, 10):
        __match_args__ = [*ast.AsyncFunctionDef.__match_args__, 'is_macro']
    is_macro: bool
    _fields = (*ast.AsyncFunctionDef._fields, 'is_macro')

    def __init__(self, *args, is_macro: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_macro = is_macro

class ClassDef(ast.ClassDef): 
    if sys.version_info >= (3, 10):
        __match_args__ = [*ast.ClassDef.__match_args__, 'is_macro']
    is_macro: bool
    _fields = (*ast.ClassDef._fields, 'is_macro')

    def __init__(self, *args, is_macro: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_macro = is_macro

type Def = FunctionDef | AsyncFunctionDef | ClassDef

class Import(ast.Import):
    if sys.version_info >= (3, 10):
        __match_args__ = [*ast.Import.__match_args__, 'is_macro']
    is_macro: bool
    _fields = (*ast.Import._fields, 'is_macro')

    def __init__(self, *args, is_macro: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_macro = is_macro

class ImportFrom(ast.ImportFrom):
    if sys.version_info >= (3, 10):
        __match_args__ = [*ast.ImportFrom.__match_args__, 'is_macro']
    is_macro: bool
    _fields = (*ast.ImportFrom._fields, 'is_macro')

    def __init__(self, *args, is_macro: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_macro = is_macro

class Code:
    __current_state: str | list[TokenInfo] | list[tuple[int, str]] | ast.AST

    def __init__(self, state: Self | str | Iterable[TokenInfo | tuple[int, str]] | ast.AST | None):
        if isinstance(state, Code):
            self.__current_state = state.__current_state
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
            return unparse(self.__current_state)
        elif isinstance(self.__current_state, Iterable):
            return untokenize(self.__current_state)
        raise TypeError(f"Current state has invalid type {type(self.__current_state)}")

    @property
    def ast(self):
        if isinstance(self.__current_state, ast.AST):
            return self.__current_state

        with StringIO(self.string) as file:
            return parse(file)

    @property
    def tokens(self):
        if isinstance(self.__current_state, Iterable) and not isinstance(self.__current_state, str):
            return self.__current_state
        # return tokenize(self.string, False)
        return tokenize(self.string)
    
    def __repr__(self):
        return f"Code({str(self.tokens)})"

MACRO_PREFIX = "__macro__"
def mangle(name: str, force: bool = False) -> str:
    # to allow keywords to be used as macro names, they must be mangled
    if iskeyword(name) or issoftkeyword(name) or force:
        return f"{MACRO_PREFIX}{name}"
    return name


def demangle(text):
    return re.sub(f"{MACRO_PREFIX}(\\w+)", "\\1!", text)

class Unparser(ast._Unparser):
    def visit_MacroName(self, node: MacroName):
        self.write(mangle(node.id))

    def visit_MacroCall(self, node: MacroCall):
        if not node.args:
            token_list = ""
        else:
            assert isinstance(node.args, UnparsedFragment)
            token_list = ', '.join(f"({token.type}, {token.string!r})" for token in node.args)
        assert isinstance(node.func, str)
        self.write(f"{mangle(node.func)}(Code([{token_list}]))")
    
    def visit_UnparsedFragment(self, node: UnparsedFragment):
        token_list = ', '.join(f"({token.type}, {token.string!r})" for token in node.data)
        self.write(f"[{token_list}]")

    def visit_TokenLiteral(self, node: TokenLiteral):
        self.visit_UnparsedFragment(node)


def parse(source, mode: str = 'file'):
    from magic_codec.macros.macro_parser import MacroPythonParser
    tokenizer = Tokenizer(generate_tokens(source.readline))
    parser = MacroPythonParser(tokenizer)
    return parser.file() if mode == 'file' else parser.eval()

def unparse(ast_obj):
    unparser = Unparser()
    return unparser.visit(ast_obj)

def to_ast(source: Code, grammar_rule: str = 'eval'):
    from magic_codec.macros.macro_parser import MacroPythonParser

    if not isinstance(source, Code):
        source = Code(source)
    
    # TODO make source.tokens usable directly
    with StringIO(source.string) as code:
        tokenizer = Tokenizer(generate_tokens(code.readline))
        parser = MacroPythonParser(tokenizer)
        if grammar_rule == 'eval':
            return parser.eval().body

        return getattr(parser, grammar_rule)()