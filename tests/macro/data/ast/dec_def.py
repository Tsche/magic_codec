@macro
def foo(): ...

@macro
def foo(): 
    ...

@macro(eval_args=True)
def foo(): ...

@macro(eval_args=True)
def foo():
    ...

@macro
class foo: ...

@macro
class foo: 
    ...

@macro(eval_args=True)
class foo: ...

@macro(eval_args=True)
class foo:
    ...