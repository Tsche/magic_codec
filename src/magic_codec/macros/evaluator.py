import ast
import copy
from importlib.machinery import PathFinder, SourceFileLoader
from importlib.util import cache_from_source
from io import StringIO
import marshal
from pathlib import Path
from token import NAME, OP
from tokenize import TokenInfo, detect_encoding, untokenize, tokenize, generate_tokens
from typing import Optional
from magic_codec.macros.ast import MACRO_PREFIX, AsyncFunctionDef, ClassDef, Code, FunctionDef, Import, ImportFrom, MacroCall, MacroName, MacroStmt, TokenLiteral, UnparsedFragment, demangle, mangle, maybe_macro, to_ast
from magic_codec.macros.interpreter import Interpreter, synthesize_call
from pegen.tokenizer import Tokenizer


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


class MacroFileLoader(SourceFileLoader):
    def __init__(self, fullname: str, path: str, macro_only: bool = False) -> None:
        super().__init__(fullname, path)
        self.macro_only = macro_only

    def process_macros(self):
        source, meta = transform(Path(self.path).read_text(), Path(self.path))
        return source, meta

    def make_macro_path(self, path: Path | str):
        path_ = Path(path)
        return path_.with_stem(f"{MACRO_PREFIX}{path_.stem}")

    def set_data(self, path: str, data, *, _mode: int = 438) -> None:
        print(f"recompiling {self.path}")
        super().set_data(path, data, _mode=_mode)

        macro_path = self.make_macro_path(path)
        macro_source_path = self.make_macro_path(self.path)
        _, macros = self.process_macros()

        # copy header from the primary cache file
        macro_data = bytearray(data[:16])
        macro_data.extend(marshal.dumps(compile(macros, macro_source_path, mode="exec")))
        super().set_data(str(macro_path), macro_data, _mode=_mode)

    def get_code(self, fullname):
        if self.macro_only:
            # try to get code for the base module
            parts = fullname.split('.')
            parts[-1] = demangle(parts[-1])
            base_name = '.'.join(parts)

            # force loading the base module code object
            # this refreshes the caches and triggers recompilation if necessary
            base_loader = MacroFileLoader(base_name, self.path, False)
            code = base_loader.get_code(base_name)

            #! note that this will fail to regenerate the macro cache
            #! if the macro cache is missing but the primary module cache 
            #! still exists and is up to date
 
        return super().get_code(fullname)

    def get_data(self, path: str) -> bytes:
        path_ = Path(path)
        if not path_.exists():
            return b''

        if path_.suffix != ".py":
            # module has already been compiled
            return super().get_data(self.make_macro_path(path) if self.macro_only else str(path))

        with open(path, 'rb') as source:
            assert self.path == str(path), f"Path mismatch {self.path} != {path}"
            # read in raw data here to force module recompilation whenever the file changes
            # regardless of if the change was made to the macro or primary module part
            return source.read()


class MacroFinder(PathFinder):
    @staticmethod
    def uses_macro_codec(path):
        with open(path, 'rb') as source:
            encoding, *_ = detect_encoding(source.readline)
            return encoding == "magic.macro"

    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        macro_only = False
        processed_name = fullname
        parts = fullname.split('.')
        if parts[-1].startswith(MACRO_PREFIX):
            # the module was imported via name! bang-name
            # => we're only interested in this module's macros
            parts[-1] = parts[-1].removeprefix(MACRO_PREFIX)
            processed_name = '.'.join(parts)
            macro_only = True

        if not (spec := super().find_spec(processed_name, path, target)):
            return

        if not (spec.origin and isinstance(spec.loader, SourceFileLoader)):
            # we cannot process macros unless we have an origin
            return

        if cls.uses_macro_codec(spec.origin):
            spec.name = fullname
            spec.loader = MacroFileLoader(fullname, spec.origin, macro_only)
            return spec


def install_import_hook():
    # This needs to be called within the macro preprocessor context
    # to allow importing macros from other modules, even if they
    # have already been compiled
    import sys
    sys.meta_path.insert(0, MacroFinder())


type Def = FunctionDef | AsyncFunctionDef | ClassDef


class Sema(ast.NodeVisitor):
    def visit_FunctionDef(self, node: FunctionDef):
        self.act_on_definition(node)

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        self.act_on_definition(node)

    def visit_ClassDef(self, node: ClassDef):
        self.act_on_definition(node)

    def act_on_definition(self, node: Def):
        ...

    def visit_Import(self, node: Import):
        ...

    def visit_ImportFrom(self, node: ImportFrom):
        ...


class MacroEvaluator(ast.NodeTransformer):
    def __init__(self, interpreter: Interpreter):
        self.interpreter = interpreter
        self.preprocessor_state = ast.Module()

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
        for statement in node.body:
            expanded_body.append(self.visit(statement))
        node.body = expanded_body

        if node.is_macro:
            # evaluate macros, ensure names are mangled
            node.name = mangle(node.name)

            self.preprocessor_state.body.append(node)
            self.interpreter.exec(Code(node))

            # discard the current node
            return None

        return node

    def visit_MacroCall(self, node: MacroCall) -> list[ast.stmt]:
        result = self.interpreter.eval(Code(node))
        return to_ast(result, 'statements')

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
            self.preprocessor_state.body.append(import_)
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
        parser = MacroPythonParser(tokenizer, filename=str(source_file))
        result = parser.start()
        if result is None:
            raise RuntimeError("Parsing failed")
        assert isinstance(result, ast.AST)
        return result


__default_globals = {
    '__name__': "__main__",
    'Token': TokenInfo,
    'macro': macro,
    'tokenize': macro(tokenize, eval_args=True),
    'untokenize': macro(untokenize, eval_args=True),
    'Code': Code
}


def transform(source: str, source_file: Path) -> tuple[ast.AST, ast.AST]:
    tree = parse(source, source_file)

    # perform semantic analysis - this is mostly for good diagnostics
    Sema().visit(tree)

    interpreter = Interpreter(__default_globals)
    interpreter.execute_fnc(install_import_hook)

    evaluator = MacroEvaluator(interpreter)
    evaluated_tree = evaluator.visit(tree)
    # print("orig")
    # print(ast.dump(tree, indent=2))
    # print("pre")
    # # print(ast.dump(evaluated_tree, indent=2))
    # print(unparse(evaluated_tree))
    # print("macro")
    # # print(ast.dump(evaluator.preprocessor_state, indent=2))
    # print(unparse(evaluator.preprocessor_state))
    return evaluated_tree, evaluator.preprocessor_state
