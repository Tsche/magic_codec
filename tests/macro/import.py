# coding: magic.macro

macro import ast
macro from token import (
    DEDENT, ENDMARKER, INDENT, NAME, 
    NEWLINE, NL, NUMBER, OP, STRING)
macro from tokenize import TokenInfo

macro def foo(code):
    print("Preprocessor globals: ", globals().keys())
    return code

@foo
def bar():
    return 2