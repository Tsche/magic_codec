import ast
from collections import UserList
from io import StringIO
from keyword import iskeyword, issoftkeyword
import re
import sys
from tokenize import TokenInfo, generate_tokens

from pegen.tokenizer import Tokenizer

class MacroCall(ast.Call): ...

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
        
        if isinstance(node.func, str):
            self.write(f"{mangle(node.func)}")
        else:
            self.visit(node.func)
        self.write(f"(_CodeArtifact([{token_list}]))")
    
    def visit_UnparsedFragment(self, node: UnparsedFragment):
        token_list = ', '.join(f"({token.type}, {token.string!r})" for token in node.data)
        self.write(f"_CodeArtifact([{token_list}])")

    def visit_TokenLiteral(self, node: TokenLiteral):
        self.visit_UnparsedFragment(node)


def parse_string(source: str, mode: str = 'file'):
    from magic_codec.grammar.macro_parser import MacroPythonParser
    tokenizer = Tokenizer(generate_tokens(StringIO(source).readline))
    parser = MacroPythonParser(tokenizer)
    return parser.file() if mode == 'file' else parser.eval()

def parse(source, mode: str = 'file'):
    from magic_codec.grammar.macro_parser import MacroPythonParser
    tokenizer = Tokenizer(generate_tokens(source.readline))
    parser = MacroPythonParser(tokenizer)
    return parser.file() if mode == 'file' else parser.eval()

def unparse(ast_obj):
    unparser = Unparser()
    return unparser.visit(ast_obj)
