# coding: magic.macro
macro import tokenize

def replace_zeroes!(code):
    for type_, string in code.tokens:
        if type_ == tokenize.NUMBER and string == '0':
            yield tokenize.NUMBER, "1"
        else:
            yield type_, string

bar! = foo!()

@replace_zeroes!
def foo(a, b = bar!):
    return (a - 0) * (b + 2.5)

if __name__ == "__main__":
    print(foo(1, 2))
