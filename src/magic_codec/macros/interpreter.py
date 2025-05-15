import ast
from token import NAME, NUMBER, STRING
from tokenize import TokenInfo, tokenize
from typing import Any, Generator, Iterable, Optional
from magic_codec.macros.macro_ast import Code

# def synthesize_token_list(tokens: list[TokenInfo], raw = False):
#     cast_to = "" if raw else "Token"
#     token_list = ', '.join(f"{cast_to}({token.type},{token.string!r})" for token in tokens)
#     code = f"[{token_list}]" if raw else f"Code([{token_list}])"
#     return Code(list(tokenize(code)))


def synthesize_call(function: Code, args: Code) -> Code:
    return Code(f"{function.string}({args.string})")

def synthesize_call_chain(calls: Iterable[Code], args: Code, convert_to: Optional[str] = None) -> Code:
    calls = list(calls)
    if not calls:
        return args
    call = synthesize_call(calls[0], synthesize_call_chain(calls[1:], args, convert_to)) if calls else args
    return synthesize_call(Code(convert_to), call) if convert_to else call


def synthesize_constant(value: Any):
    if value is None:
        return
    elif isinstance(value, TokenInfo):
        if value.string == "None":
            return
        yield value
    elif isinstance(value, tuple):
        if len(value) != 2:
            raise RuntimeError("Can only return (str, int) 2-tuples in place of tokens")
        if value[1] == "None":
            return
        yield (int(value[0]), str(value[1]))
    elif isinstance(value, bool):
        yield (NAME, str(value))
    elif isinstance(value, (int, float)):
        yield (NUMBER, str(value))
    elif isinstance(value, str):
        try:
            node = ast.parse(value, mode="eval")
            if isinstance(node.body, ast.Constant):
                yield (STRING, value)
            elif isinstance(node.body, ast.Name):
                yield (NAME, value)
            else:
                # string contains more than one token - insert all of them into the token stream
                raise RuntimeError
        except RuntimeError:
            yield from tokenize(value)
    elif isinstance(value, (list, Generator)):
        # directly inject tokens into token stream
        for item in value:
            if not isinstance(item, (TokenInfo, tuple)):
                raise RuntimeError("Expected list or generator of tokens to directly inject into the token stream")
            yield from synthesize_constant(item)
    else:
        # couldn't find something to replace the constant with
        raise RuntimeError(f"Unexpected macro return value {type(value)}")

class Interpreter:
    def __init__(self, globals: dict[str, Any]):
        self.__default_globals = globals.copy()
        self.globals: dict[str, Any] = globals
        self.module = ast.Module()

    def execute_fnc(self, fnc, *args, **kwargs):
        self.exec(Code("__fn(*__args, **__kwargs)"), {'__fn': fnc, '__args': args, '__kwargs': kwargs}, memoize=False)

    def reset(self):
        self.globals = self.__default_globals
        self.macros = {}

    def push_code(self, tree: ast.AST):
        if isinstance(tree, ast.Module):
            self.module.body.extend(tree.body)
        else:
            self.module.body.append(tree)

    def exec(self, code: Code, locals=None, memoize=True):
        # print("exec: ", code.string)
        if memoize:
            self.push_code(code.ast)
        exec(code.string, self.globals, locals or self.globals)

    def eval(self, code: Code, locals=None):
        # print("eval: ", code.string) #, end=" -> ")
        ret = eval(code.string, self.globals, locals or self.globals)
        # print(ret)
        return ret

    def apply_macros(self, code: Code, macros: Iterable[Code]):
        call = synthesize_call_chain(macros, args=Code("__magic_macro_code_object"), convert_to="_CodeArtifact")
        call_locals = {'__magic_macro_code_object': Code(code)}
        return self.eval(call, call_locals)