import ast
import warnings

from magic_codec.macros.evaluator import Def
from magic_codec.macros.macro_ast import AsyncFunctionDef, ClassDef, FunctionDef, Import, ImportFrom, MacroCall
from magic_codec.macros.parser import Parser


class Sema(ast.NodeVisitor):
    def __init__(self, parser: Parser):
        self.parser = parser

    def visit_Module(self, node: ast.Module):
        for statement in node.body:
            if isinstance(statement, (FunctionDef, AsyncFunctionDef, ClassDef)):
                # only allow macro definitions at module scope
                # getattr(self, f"visit_{statement.__class__.__name__}")(statement, allow_macros=True)
                self.act_on_definition(statement, allow_macros=True)
            else:
                self.visit(statement)

    def visit_FunctionDef(self, node: FunctionDef):
        self.act_on_definition(node, allow_macros=False)

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        self.act_on_definition(node, allow_macros=False)

    def visit_ClassDef(self, node: ClassDef):
        self.act_on_definition(node, allow_macros=False)

    def act_on_definition(self, node: Def, allow_macros=False):
        if node.is_macro and not allow_macros:
            self.parser.raise_syntax_error_known_location(
                "Macros may only be defined at module scope", node)
        self.generic_visit(node)

    def visit_Import(self, node: Import):
        ...

    def visit_ImportFrom(self, node: ImportFrom):
        ...
