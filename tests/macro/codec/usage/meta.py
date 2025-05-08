# coding: magic.macro

@macro
def define_macro(name: str, fnc):
    from magic_codec.macro import mangle
    globals()[mangle(name)] = fnc

@macro(eval_args=True)
def foo():
    define_macro("bar", lambda x: x)

foo!()

x = bar!(3)
