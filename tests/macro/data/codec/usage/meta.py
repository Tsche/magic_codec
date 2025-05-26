# coding: magic.macro

@macro
def define_macro(name: str, fnc):
    # injects a function into the preprocessor
    # however, these macros will not get cached for imports
    globals()[name] = fnc

@macro(eval_args=True)
def foo():
    define_macro("bar", lambda x: x)

foo!()

x = bar!(3)
