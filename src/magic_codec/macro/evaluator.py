import logging
import ast
from io import StringIO
from pathlib import Path
import sys
import time
from tokenize import TokenInfo, untokenize, tokenize, generate_tokens
import traceback
from typing import Any, Generator, Iterable, Optional
from magic_codec.macro.macro_ast import (MACRO_PREFIX, AsyncFunctionDef, ClassDef, FunctionDef, Import,
                                         ImportFrom, MacroCall, MacroName, TokenLiteral, UnparsedFragment,
                                         mangle, Def, TreePass)

from magic_codec.macro.code import Code, Token, to_ast
from pegen.tokenizer import Tokenizer


logger = logging.getLogger(__name__)


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


def synthesize_call(function: Code, args: Code) -> Code:
    return Code(f"{function.string}({args.string})")


def synthesize_call_chain(calls: Iterable[Code], args: Code, convert_to: Optional[str] = None) -> Code:
    calls = list(calls)
    if not calls:
        return args
    call = synthesize_call(calls[0], synthesize_call_chain(calls[1:], args, convert_to)) if calls else args
    return synthesize_call(Code(convert_to), call) if convert_to else call


class MacroEvaluator(TreePass):
    def __init__(self):
        self.globals: dict[str, Any] = {
            '__name__': "__main__",
            'macro': macro,
            # 'tokenize': macro(tokenize, eval_args=True),
            # 'untokenize': macro(untokenize, eval_args=True),
            'macro_rules': self.macro_rules,
            '_make_macro': self.make_macro,
            '_Token': Token,
            '_Code': Code
        }

        self.module = ast.Module()
        self.exec(Code("from magic_codec.macro.hooks import register_imports"))

    def make_macro(self, code: Code):
        # statements = code.to("statements")
        # preprocessed = Code(self.visit_multiple(statements))
        self.exec(code)

    def macro_rules(self, unparsed_name):
        # parse name, ensure it is a valid Python identifier
        name = unparsed_name.to("name").string
        def parse_rules(rules):
            from magic_codec.macro.declarative import make_parser
            parser = make_parser(name, rules.tokens)
            self.make_macro(Code(parser))
            self.make_macro(Code(f"""
def {name}(code):
    from magic_codec.macro.declarative import to_tokenizer
    try:
        return _Code(_{name}_Parser(to_tokenizer(code)).{name}())
    except StopIteration:
        raise RuntimeError(f"Invalid declarative macro use: {name}!({{code.string}})")
"""))
        return parse_rules


    def push_code(self, tree: ast.AST):
        if isinstance(tree, ast.Module):
            self.module.body.extend(tree.body)
        else:
            self.module.body.append(tree)

    def exec(self, code: Code, locals=None, memoize=True):
        logger.debug(f"EXEC: \n{code.string}")
        if memoize:
            self.push_code(code.ast)
        start = time.time()
        exec(code.string, self.globals, locals or self.globals)
        end = time.time()
        logger.debug(f"FINISHED IN: {int((end - start) * 1000)}ms")

    def eval(self, code: Code, locals=None):
        start = time.time()
        ret = eval(code.string, self.globals, locals or self.globals)
        end = time.time()
        logger.debug(f"EVAL: {code.string}")
        logger.debug(f"FINISHED IN: {int((end - start) * 1000)}ms")
        return ret

    def apply_macros(self, code: Code, macros: Iterable[Code]):
        call = synthesize_call_chain(macros, args=Code("__magic_macro_code_object"), convert_to="_Code")
        call_locals = {'__magic_macro_code_object': Code(code)}
        return self.eval(call, call_locals)

    def visit_Module(self, node: ast.Module):
        stmts: list[ast.stmt] = []
        for statement in node.body:
            if isinstance(statement, (FunctionDef, AsyncFunctionDef, ClassDef)):
                # only allow macro definitions at module scope
                stmts.extend(self.act_on_definition(statement, allow_macros=True))
            else:
                stmts.extend(self.visit(statement))
        yield ast.Module(body=stmts, type_ignores=node.type_ignores)

    def visit_FunctionDef(self, node: FunctionDef):
        yield from self.act_on_definition(node)

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        yield from self.act_on_definition(node)

    def visit_ClassDef(self, node: ClassDef):
        yield from self.act_on_definition(node)

    def act_on_definition(self, node: Def, allow_macros=False) -> Generator[Def]:
        if node.is_macro and not allow_macros:
            self.report_error("Macro definitions are only allowed at module scope")

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
            self.exec(Code(node))

            # discard the current node
            return

        yield node

    def report_error(self, message: str, node: Optional[ast.AST] = None):
        print(message)
        sys.exit()

    def visit_MacroCall(self, node: MacroCall) -> Generator[ast.stmt]:
        try:
            result = self.eval(Code(node))
        except Exception:
            self.report_error(f"Macro evaluation failed!\n\n{traceback.format_exc()}", node)

        if not result:
            return
        statements = to_ast(result, 'statements')
        if statements:
            yield from self.visit_multiple(statements)

    def visit_MacroName(self, node: MacroName):
        raise RuntimeError("Macro names cannot appear in this context")

    def visit_TokenLiteral(self, node: TokenLiteral) -> Generator[ast.List]:
        tokens = ', '.join(f"({token.type}, {token.string!r})" for token in node.data)
        yield Code(f"_Code([{tokens}])").to("primary")

    def visit_Import(self, node: Import):
        # TODO implement
        if not node.is_macro:
            # also check module, names and aliases
            yield node

    def target_macro_module(self, name: str):
        module = name.split('.')
        module[-1] = f"{MACRO_PREFIX}{module[-1]}"
        return '.'.join(module)

    def visit_ImportFrom(self, node: ImportFrom) -> Generator[ast.ImportFrom]:
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
            self.exec(Code(import_))

        if names:
            yield ast.ImportFrom(node.module, names, node.level,
                                 lineno=node.lineno,
                                 col_offset=node.col_offset,
                                 end_lineno=node.end_lineno,
                                 end_col_offset=node.end_col_offset)
        return


def parse(source: str, source_file: Path | None) -> ast.AST:
    from magic_codec.parser.macro import MacroParser
    with StringIO(source) as file:
        tokenizer = Tokenizer(generate_tokens(file.readline))
        parser = MacroParser(tokenizer, verbose=False, filename=str(source_file) if source_file else "")
        result = parser.start()
        if result is None:
            err = parser.make_syntax_error(str(source_file or "<src>"))
            traceback.print_exception(err.__class__, err, None)
            sys.exit(1)
        assert isinstance(result, ast.AST)
        return result


def transform(source: str, source_file: Path | None) -> tuple[ast.AST, ast.AST]:
    tree = parse(source, source_file)
    evaluator = MacroEvaluator()
    evaluated_tree = evaluator.evaluate(tree)
    return evaluated_tree, evaluator.module
