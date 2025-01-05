# coding: magic.macro

@macro
def finally!(code):
    yield from tokenize("except: raise\n")
    yield from tokenize("finally:")
    yield from code.tokens

@macro
def used_in_macro(code):
    try:
        print("zoinks")
    finally!:
        yield from code.tokens

try:
    print("x")
finally!:
    print("hi")
print()