# coding: magic.macro

from functools import cache

@macro
def foo(tokens):
    return tokens

@cache
@foo!
def target():
    ...