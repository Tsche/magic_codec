# coding: magic.macro

@macro
def finally!(code):
    # yield from `except: raise`
    yield from [(1, 'except'), (55, ''), (1, 'raise')]
    yield (4, '\n')
    # yield from `finally:`
    yield from code.tokens

# @macro
# def used_in_macro(code):
#     try:
#         print("zoinks")
#     finally!:
#         yield from code.tokens

try:
    print("x")
finally!:
    print("hi")