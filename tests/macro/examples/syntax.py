# coding: magic.macro

macro from typing_extensions import deprecated

macro def foo(code):
    print(code.string)
    return code

@deprecated("foo")
@macro
@foo
def bar(code):
    print(code.string)
    return code

@bar
def zoinks():
    return 3
