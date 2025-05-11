import ast
import copy
from importlib.machinery import PathFinder, SourceFileLoader
from io import StringIO
from pathlib import Path
from token import NAME, OP
from tokenize import detect_encoding, untokenize, tokenize, generate_tokens
from magic_codec.macros.ast import *
from magic_codec.macros.interpreter import Interpreter, synthesize_call
from magic_codec.macros.macro_parser import MacroPythonParser
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
                call = synthesize_call([(NAME, "self"), (OP, '.'), (NAME, 'fnc')], 
                                       list(code_object.tokens))
                return eval(untokenize(call), globals(), locals())
            return self.fnc(*args, **kwds)

    return Macro(fnc) if fnc else Macro

class MacroFileLoader(SourceFileLoader):
    def __init__(self, fullname: str, path: str, macro_only: bool = False) -> None:
        super().__init__(fullname, path)
        self.macro_only = macro_only

    def process_macros(self):
        print(self.path)

    def set_data(self, path: str, data, *, _mode: int = 438) -> None:
        print("set: ", path)
        return super().set_data(path, data, _mode=_mode)

    def get_data(self, path: str) -> bytes:
        print("get: ", path)
        if not os.path.exists(path):
            return b''

        if not path.endswith(".py"):
            # module has already been compiled
            self.process_macros()
            return super().get_data(path)

        with open(path, 'rb') as source:
            assert self.path == path, "Actual path isn't the expected original module path, but ends in .py"
            self.process_macros()
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
        parts = fullname.split('.')
        if parts[-1].startswith(MACRO_PREFIX):
            # the module was imported via name! bang-name
            # => we're only interested in this module's macros
            parts[-1] = parts[-1].removeprefix(MACRO_PREFIX)
            fullname = '.'.join(parts)
            macro_only = True

        if not (spec := super().find_spec(fullname, path, target)):
            return

        if not (spec.origin and isinstance(spec.loader, SourceFileLoader)):
            # we cannot process macros unless we have an origin
            return

        if cls.uses_macro_codec(spec.origin):
            spec.loader = MacroFileLoader(fullname, spec.origin, macro_only)
            return spec

def install_import_hook():
    # This needs to be called within the macro preprocessor context
    # to allow importing macros from other modules, even if they
    # have already been compiled
    sys.meta_path.insert(0, MacroFinder())

class MacroEvaluator(ast.NodeTransformer):
    def __init__(self, interpreter: Interpreter):
        self.interpreter = interpreter
        self.preprocessor_state = ast.Module()

    def generic_visit(self, node):
        # do not modify tree in place
        return super().generic_visit(copy.deepcopy(node))

    type T = FunctionDef | AsyncFunctionDef | ClassDef
    def act_on_definition(self, node: T) -> T:
        if isinstance(node.body, UnparsedFragment):
            # must evaluate
            macro_decorators = [Code(decorator) for decorator in node.decorator_list if isinstance(decorator, (MacroCall, MacroName))]
            node.decorator_list = [decorator for decorator in node.decorator_list if not isinstance(decorator, (MacroCall, MacroName))]
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
            self.interpreter.exec(Code(node))
            
            self.preprocessor_state.body.append(node)
            # discard the current node
            return None

        return node

    def visit_FunctionDef(self, node: FunctionDef):
        return self.act_on_definition(node)
    
    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        return self.act_on_definition(node)
    
    def visit_ClassDef(self, node: ClassDef):
        return self.act_on_definition(node)
    
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
    
def parse(source: str, source_file: Path) -> ast.AST:
    with StringIO(source) as file:
        tokenizer = Tokenizer(generate_tokens(file.readline))
        parser = MacroPythonParser(tokenizer, filename=source_file)
        return parser.start()

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
    
    interpreter = Interpreter(__default_globals)
    interpreter.execute_fnc(install_import_hook)

    evaluator = MacroEvaluator(interpreter)
    evaluated_tree = evaluator.visit(tree)
    print("orig")
    print(ast.dump(tree, indent=2))
    print("pre")
    print(unparse(evaluated_tree))
    print("macro")
    print(unparse(evaluator.preprocessor_state))

    return evaluated_tree, evaluator.preprocessor_state