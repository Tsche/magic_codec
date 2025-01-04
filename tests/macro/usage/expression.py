# coding: magic.macro


# def zoinks!(tokens): return "return   42"
# x = 2

# def bar!():
#     return 42

# @macro
# def foo!(x: int):
#     def bar():
#         return 7
#     return x * bar!() * bar()

# baz! = bar!() * 2

# class Test:
#     def bar(x):
#         return baz!

#     @zoinks!
#     def boings(): ...

# FOO = foo!(42)
# BAZ = baz!


@macro
def test(tokens):
    print(tokens)
    return "2 + 2"

FOO = test!(42)
print(FOO)