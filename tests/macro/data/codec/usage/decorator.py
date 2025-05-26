# coding: magic.macro

from functools import cache

@macro
def foo(tokens):
    return tokens

@macro
@foo!
def bar(tokens):
    return "print(" + str(foo!(42 + 2)) + ")\n"

@cache
@foo!
@bar!
def target():
    ...
    
target()
target()