# coding: magic.macro


def zoinks!(tokens): return "return   42"
x = 2

@macro(eval_args=True)
def foo(x: int):
    def bar():
        return 7
    return x * bar()

FOO = foo!(42)

@macro
def bar(x: Code):
    return foo!(2 - 1) + foo(x)

BAR = bar!(42)
