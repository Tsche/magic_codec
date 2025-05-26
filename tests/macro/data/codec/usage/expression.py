# coding: magic.macro


def zoinks!(_): return "return   42"
x = 2

@macro(eval_args=True)
def foo(x: int):
    def bar():
        return 7
    return x * bar()

FOO = foo!(42)

@macro
def bar(x):
    return foo!(5 * 10) + foo(x)

BAR = bar!(42)
