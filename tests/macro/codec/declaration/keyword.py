# coding: magic.macro

macro def foo(tokens):
    return tokens

macro async def foo_async2(tokens):
    return tokens

async macro def foo_async(tokens):
    return tokens

macro class Bar: ...

macro x = 42