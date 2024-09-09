# coding: magic.macro
macro def zoinks(code):
    yield from code.tokens

@macro
def foo(test=3):
    def wrap(code):
        return code
    return wrap

foo = a @ b
bar @= c

@identity(foo="bar")
@foo(42)
@boo.z
@zoinks
def bar():
    return 3

if __name__ == "__main__":
    print(bar())