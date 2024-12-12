# coding: magic.macro

macro fn   = "def"
macro main = 'if __name__ == "__main__"'

fn foo(x: int):
    return x * 2

main:
    print(f"{foo(4)}")