# coding: magic.macro

# @macro
# def foo(): ...

# from! bar.provides_macro import foo

from bar.__macro__provides_macro import foo

print("hi")