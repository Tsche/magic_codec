# coding: magic.macro
macro import tokenize

macro def replace_zeroes(code):
    for type_, string in code.tokens:
        if type_ == tokenize.NUMBER and string == '0':
            yield tokenize.NUMBER, "1"
        else:
            yield type_, string

@macro
def zoinks(a, b):
    return a + b

@replace_zeroes
def foo(a, b):
    return (a - 0) * (b + 2.5)

if __name__ == "__main__":
    print(foo(1, 2))
    print(zoinks(1, 10))

