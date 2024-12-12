# coding: magic.macro

@macro
def foo(x: int):
    return x * 7

bar! = 42

FOO = foo!(42)
BAR = bar!