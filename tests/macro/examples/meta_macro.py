# coding: magic.macro

@macro
def make_macro(source):
    exec(source.string, globals(), globals())

make_macro!(def foo(_): return "42")

foo!(23)