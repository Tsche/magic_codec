# coding: magic.macro
macro def foo(code):
    return "assert True\n"
# this is line 4
@foo
def bar(): 
    ...

