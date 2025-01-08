# coding: magic.macro

from functools import cache

@macro
def foo(tokens):
    return tokens.tokens

@macro
def bar(tokens):
    return "return " + str(foo!(42 + 2))

@cache
@foo!
@bar!
def target():
    ...

target()
target()