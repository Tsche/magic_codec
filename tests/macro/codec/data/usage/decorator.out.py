from functools import cache

@cache
def target():
    print(44)
target()
target()
