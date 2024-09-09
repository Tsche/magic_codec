# coding: magic.macro

macro class Foo:
    def __init__(self, zoinks): ...

    def bar(self):
        return 1.23

macro def compute(foo: int, bar: int = 42):
    return foo * bar

macro FOO = compute(23, bar=12)

def bar():
    print(FOO)