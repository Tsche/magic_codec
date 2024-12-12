# coding: magic.macro
@macro(kind="statement")
def try!(tokens):
    yield from tokens

@macro(kind="statement", after="try!")
def finally!(tokens):
    yield from tokens

try!:
    print("x")
finally!:
    ...