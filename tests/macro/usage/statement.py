# coding: magic.macro
@macro(kind="statement")
def try!(code):
    yield from tokenize("try:")
    yield from code.tokens

@macro(kind="statement", after=try!)
def finally!(code):
    yield from tokenize("catch:raise\n")
    yield from tokenize("finally:")
    yield from code.tokens

try!:
    print("x")
finally!: 
    ...
print()