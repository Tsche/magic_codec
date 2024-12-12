# coding: magic.macro

# imports non-macros in the context of the macro preprocessor

macro import token as t
macro import token

macro from token import DEDENT as D
macro from token import INDENT

macro from .macro.foo import FOO
