# coding: magic.macro

def foo!(tokens):
    return tokens

class Bar!: ...

# error: this is a macro use of x!
#x! = 42