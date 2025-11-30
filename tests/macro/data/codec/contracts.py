# coding: magic.macro


@macro
def pre(condition):
    def wrap_fnc(fnc):
        stringified = condition.string.replace('"', '\'')
        yield from [_Token(1, "assert"), *condition.tokens, _Token(55, ','),
                    _Token(3, f'"Precondition `{stringified}` failed"'), _Token(4, '\n')]
        yield from fnc.tokens
    return wrap_fnc


@macro
def post(condition):
    def get_var_name(id: int):
        return f"__mm_retval{id}"

    def make_assertion(replacement: str):
        tokens = [_Token(1, replacement) if token == _Token(55, '$') else token
                  for token in condition.tokens]
        stringified = _Code(tokens).string.replace('"', '\'')
        assertion = _Code([_Token(1, "assert"), *tokens, _Token(55, ','),
                           _Token(3, f'"Precondition `{stringified}` failed"'), _Token(4, '\n')]).to("assert_stmt")
        return assertion

    def wrap_fnc(fnc):
        # print(fnc)

        name = get_var_name(0)
        assertion = make_assertion(name)
        statements = fnc.to("statements")
        print(fnc.to("statements"))
        # assertion = condition.to("expression")
        # print(stringified, assertion)
        yield from fnc.tokens
    return wrap_fnc


@macro
def strict(code):
    # print(code)
    yield from code.tokens


@pre!(x > 5 and y != "foo")
@post!($ <= 2)
@strict!
def foo(x: int, y: str) -> int:
    if (x == 6):
        return x / 3
    return 0


if __name__ == "__main__":
    foo(6, "bar")
