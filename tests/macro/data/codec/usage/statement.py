# coding: magic.macro

@macro
def with_args(code, unparsed_args):
    yield unparsed_args
    yield '\n'
    yield code

with_args! x = 2:
    print(f"foo {x}")
    print("bar")
print("x")


@macro
def in_macro():
    with_args! x = 3:
        yield f"print({x})"

in_macro!()
