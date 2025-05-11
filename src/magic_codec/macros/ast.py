import ast
from collections import UserList
import sys
from tokenize import TokenInfo
from typing import TypeVar, Union


class MacroFunctionDef(ast.FunctionDef): ...
class MacroAsyncFunctionDef(ast.AsyncFunctionDef): ...
class MacroClassDef(ast.ClassDef): ...

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

class MacroName(ast.Name): ...

class UnparsedFragment(UserList, ast.AST):
    if sys.version_info >= (3, 10):
        __match_args__ = ("tokens")

    data: list[TokenInfo]
    _fields = ("data",)

class TokenLiteral(UnparsedFragment): ...


FC = TypeVar("FC", ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, MacroFunctionDef, MacroAsyncFunctionDef)
