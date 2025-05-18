import ast
from io import StringIO
from pathlib import Path
import sys
from tokenize import TokenInfo, untokenize, tokenize, generate_tokens
import traceback
from typing import Optional
from magic_codec.macro.macro_ast import (MACRO_PREFIX, AsyncFunctionDef, ClassDef, Code, FunctionDef, Import,
                                          ImportFrom, MacroCall, MacroName, TokenLiteral, UnparsedFragment, 
                                          mangle, to_ast, Def)
from magic_codec.macro.interpreter import Interpreter, synthesize_call
from pegen.tokenizer import Tokenizer

from magic_codec.macro.sema import Sema


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

class TreePass:
    def evaluate(self, tree):
        result = list(self.visit(tree))
        assert len(result) == 1
        return ast.fix_missing_locations(result[0])

    def visit(self, node):
        """Visit a node."""
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        yield from visitor(node)

    def visit_multiple(self, nodes: list):
        for node in nodes:
            yield from self.visit(node)

    def generic_visit(self, node):
        """Called if no explicit visitor function exists for a node."""
        if node is None:
            return

        new_fields = {}
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                new_fields[field] = list(self.visit_multiple(value))
            elif isinstance(value, ast.AST):
                new_value = list(self.visit(value))
                if not new_value:
                    continue
                assert len(new_value) == 1, f"Expected only one subtree, got {len(new_value)}"
                new_fields[field] = new_value[0]
            else:
                new_fields[field] = value

        yield type(node)(**new_fields)

    def visit_Expr(self, node):
        # ensure empty expressions are removed and nested exprs expanded
        for replacement in self.visit(node.value):
            if isinstance(replacement, ast.Expr):
                yield replacement
            else:
                yield ast.Expr(replacement)

class MacroEvaluator(TreePass):
    def __init__(self, interpreter: Interpreter):
        self.interpreter = interpreter
        self.interpreter.globals["__make_macro"] = self.make_macro

    def make_macro(self, code: Code):
        # statements = code.to("statements")
        # preprocessed = Code(self.visit_multiple(statements))
        self.interpreter.exec(code)

    # def generic_visit(self, node):
    #     # do not modify tree in place
    #     return super().generic_visit(copy.deepcopy(node))

    # def visit_Module(self, node: ast.Module):
    #     fixup_builtins = Code("import magic_codec.macro.hooks.register_builtins").to("import_stmt")
    #     body = [fixup_builtins, *self.visit_multiple(node.body)]
    #     yield ast.Module(body, node.type_ignores)
        

    def visit_FunctionDef(self, node: FunctionDef):
        yield from self.act_on_definition(node)

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        yield from self.act_on_definition(node)

    def visit_ClassDef(self, node: ClassDef):
        yield from self.act_on_definition(node)

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
        if node.body:
            node.body = list(self.visit_multiple(node.body))

        if node.is_macro:
            # evaluate macros, ensure names are mangled
            node.name = mangle(node.name)
            self.interpreter.exec(Code(node))

            # discard the current node
            return

        yield node

    def report_error(self, message: str, node: Optional[ast.AST] = None):
        print(message)
        sys.exit()

    def visit_MacroCall(self, node: MacroCall) -> list[ast.stmt]:
        try:
            result = self.interpreter.eval(Code(node))
        except Exception:
            self.report_error(f"Macro evaluation failed!\n\n{traceback.format_exc()}", node)

        if not result: return
        statements =  to_ast(result, 'statements')
        if statements:
            yield from self.visit_multiple(statements)

    def visit_MacroName(self, node: MacroName):
        raise RuntimeError("Macro names cannot appear in this context")

    def visit_TokenLiteral(self, node: TokenLiteral) -> ast.List:
        tokens = ', '.join(f"({token.type}, {token.string!r})" for token in node.data)
        yield Code(f"_CodeArtifact([{tokens}])").to("primary")

    def visit_Import(self, node: Import):
        if not node.is_macro:
            # also check module, names and aliases
            yield node

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
            yield ast.ImportFrom(node.module, names, node.level,
                                  lineno=node.lineno,
                                  col_offset=node.col_offset,
                                  end_lineno=node.end_lineno,
                                  end_col_offset=node.end_col_offset)
        return


def parse(source: str, source_file: Path) -> ast.AST:
    from magic_codec.grammar.macro_parser import MacroPythonParser
    with StringIO(source) as file:
        tokenizer = Tokenizer(generate_tokens(file.readline))
        parser = MacroPythonParser(tokenizer, verbose=False, filename=str(source_file))
        result = parser.start()
        if result is None:
            err = parser.make_syntax_error(str(source_file))
            traceback.print_exception(err.__class__, err, None)
            sys.exit(1)
        assert isinstance(result, ast.AST)
        return result, parser


__default_globals = {
    '__name__': "__main__",
    'Token': TokenInfo,
    'macro': macro,
    'tokenize': macro(tokenize, eval_args=True),
    'untokenize': macro(untokenize, eval_args=True),
}


def transform(source: str, source_file: Path) -> tuple[ast.AST, ast.AST]:
    tree, parser = parse(source, source_file)
    # print("=================== TREE ===================")
    # print(ast.dump(tree, indent=2))
   
    # # perform semantic analysis - this is mostly for good diagnostics
    # Sema(parser).visit(tree)

    interpreter = Interpreter(__default_globals)
    interpreter.exec(Code("from magic_codec.macro.hooks import register_builtins, register_imports"))
    # interpreter.execute_fnc(install_import_hook)

    evaluator = MacroEvaluator(interpreter)
    evaluated_tree = evaluator.evaluate(tree)
    return evaluated_tree, interpreter.module
