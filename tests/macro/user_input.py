# coding: magic.macro
macro import tokenize
macro import ast
macro from getpass import getpass

macro def read_pass(code):
    password = getpass("Codec password: ")
    for token in code.tokens:
        if token == (tokenize.NAME, 'PASS'):
            yield tokenize.NAME, f"'{password}'"
        else:
            yield token

macro def entrypoint(code):
    function_def = code.ast.body[0]
    assert isinstance(function_def, ast.FunctionDef)

    yield from code.tokens
    yield from get_tokens(f"""
if __name__ == '__main__':
    {function_def.name}()
""")

@entrypoint
@read_pass
def main():
    print(PASS)
