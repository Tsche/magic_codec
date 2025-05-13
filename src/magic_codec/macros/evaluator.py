import ast
import copy
import marshal
from importlib.machinery import PathFinder, SourceFileLoader
from io import StringIO
from pathlib import Path
from tokenize import TokenInfo, detect_encoding, untokenize, tokenize, generate_tokens
from typing import Optional
from magic_codec.macros.macro_ast import (MACRO_PREFIX, AsyncFunctionDef, ClassDef, Code, FunctionDef, Import,
                                          ImportFrom, MacroCall, MacroName, MacroStmt, TokenLiteral, UnparsedFragment, 
                                          demangle, mangle, to_ast, Def, unparse)
from magic_codec.macros.interpreter import Interpreter, synthesize_call
from pegen.tokenizer import Tokenizer

from magic_codec.macros.sema import Sema


def macro(fnc=None, /, eval_args=False, **kwargs):
    """ This decorator does nothing. It is only used to flag functions and classes as macros. """

    class Macro:
        def __init__(self, func):
            nonlocal kwargs
            self.fnc = func
            self.options = kwargs

        def __call__(self, *args, **kwds):
            if eval_args and not kwargs and len(args) == 1 and isinstance(args[0], Code):
                # only received a single argument of code type
                code_object: Code = args[0]
                call = synthesize_call(Code("self.fnc"), code_object)
                return eval(call.string, globals(), locals())
            return self.fnc(*args, **kwds)

    return Macro(fnc) if fnc else Macro

class MacroEvaluator(ast.NodeTransformer):
    def __init__(self, interpreter: Interpreter):
        self.interpreter = interpreter
        self.interpreter.globals["push_macro"] = self.push_macro

    def push_macro(self, code: Code | list[TokenInfo]):
        if not isinstance(code, Code):
            code = Code(code)
        self.interpreter.push_code(self.visit(code.ast))

    def generic_visit(self, node):
        # do not modify tree in place
        return super().generic_visit(copy.deepcopy(node))

    def visit_FunctionDef(self, node: FunctionDef):
        return self.act_on_definition(node)

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        return self.act_on_definition(node)

    def visit_ClassDef(self, node: ClassDef):
        return self.act_on_definition(node)

    def act_on_definition(self, node: Def) -> Optional[Def]:
        if isinstance(node.body, UnparsedFragment):
            # must evaluate
            macro_decorators = [Code(decorator)
                                for decorator in node.decorator_list if isinstance(decorator, (MacroCall, MacroName))]
            node.decorator_list = [decorator for decorator in node.decorator_list if not isinstance(
                decorator, (MacroCall, MacroName))]
            transformed = self.interpreter.apply_macros(Code(node.body), macro_decorators)
            node.body = to_ast(transformed, "block")

        assert not isinstance(node.body, UnparsedFragment)

        # expand macros in body
        expanded_body = []
        if node.body:
            for statement in node.body:
                after = self.visit(statement)
                expanded_body.append(after)
        node.body = expanded_body

        if node.is_macro:
            # evaluate macros, ensure names are mangled
            node.name = mangle(node.name)
            self.interpreter.exec(Code(node))

            # discard the current node
            return None

        return node

    def visit_MacroCall(self, node: MacroCall) -> list[ast.stmt]:
        result = self.interpreter.eval(Code(node))
        statements =  to_ast(result, 'statements')
        print(statements)
        return statements

    def visit_MacroStmt(self, node: MacroStmt) -> list[ast.stmt]:
        fnc = Code(node.expr)
        result = self.interpreter.apply_macros(node.body, [fnc])
        return to_ast(result, 'statements')

    def visit_MacroName(self, node: MacroName):
        raise RuntimeError("Macro names cannot appear in this context")

    def visit_TokenLiteral(self, node: TokenLiteral) -> ast.List:
        tokens = ', '.join(f"({token.type}, '{token.string}')" for token in node.data)
        return to_ast(f"[{tokens}]", "list")

    def visit_Import(self, node: Import):
        if not node.is_macro:
            # also check module, names and aliases
            return node

    def visit_Expr(self, node: ast.Expr):
        # ensure empty expressions are removed
        after = self.visit(node.value)
        if after is None:
            return None
        return ast.Expr(after)

    def target_macro_module(self, name: str):
        module = name.split('.')
        module[-1] = f"{MACRO_PREFIX}{module[-1]}"
        return '.'.join(module)

    def visit_ImportFrom(self, node: ImportFrom) -> Optional[ast.ImportFrom]:
        if isinstance(node.module, MacroName):
            # we are only allowed to import macros in preprocessor context
            node.module = self.target_macro_module(node.module.string)
            node.is_macro = True

        macro_names = []
        names = []
        for name in node.names:
            if node.is_macro or isinstance(name.name, MacroName) or isinstance(name.asname, MacroName):
                macro_names.append(name)
            else:
                names.append(name)

        if macro_names:
            import_ = ast.ImportFrom(node.module, macro_names, node.level,
                                     lineno=node.lineno,
                                     col_offset=node.col_offset,
                                     end_lineno=node.end_lineno,
                                     end_col_offset=node.end_col_offset)
            self.interpreter.exec(Code(import_))

        if names:
            return ast.ImportFrom(node.module, names, node.level,
                                  lineno=node.lineno,
                                  col_offset=node.col_offset,
                                  end_lineno=node.end_lineno,
                                  end_col_offset=node.end_col_offset)
        return None


def parse(source: str, source_file: Path) -> ast.AST:
    from magic_codec.macros.macro_parser import MacroPythonParser
    with StringIO(source) as file:
        tokenizer = Tokenizer(generate_tokens(file.readline))
        parser = MacroPythonParser(tokenizer, verbose=False, filename=str(source_file))
        result = parser.start()
        if result is None:
            raise RuntimeError("Parsing failed")
        assert isinstance(result, ast.AST)
        return result, parser


__default_globals = {
    '__name__': "__main__",
    'Token': TokenInfo,
    'macro': macro,
    'tokenize': macro(tokenize, eval_args=True),
    'untokenize': macro(untokenize, eval_args=True),
    'Code': Code
}


def transform(source: str, source_file: Path) -> tuple[ast.AST, ast.AST]:
    tree, parser = parse(source, source_file)
    print("orig")
    print(ast.dump(tree, indent=2))
   
    # # perform semantic analysis - this is mostly for good diagnostics
    # Sema(parser).visit(tree)

    interpreter = Interpreter(__default_globals)
    # interpreter.exec(Code("from magic_codec.macros.importlib import install_import_hook\ninstall_import_hook()"))
    # # interpreter.execute_fnc(install_import_hook)

    evaluator = MacroEvaluator(interpreter)
    evaluated_tree = evaluator.visit(tree)
    
    print("pre")
    print(ast.dump(evaluated_tree, indent=2))
    # print(unparse(evaluated_tree))
    # print("macro")
    # print(ast.dump(interpreter.module, indent=2))
    # print(unparse(interpreter.module))
    return None, None
    # return evaluated_tree, interpreter.module
