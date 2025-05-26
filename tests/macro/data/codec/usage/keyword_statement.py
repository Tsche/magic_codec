# coding: magic.macro

# TODO this needs grammar fixes

@macro
def finally!(code):
    yield _Code("except: raise\n").tokens
    yield _Code("finally:\n").tokens
    yield code.tokens

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