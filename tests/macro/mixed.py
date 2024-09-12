# coding: magic.macro

macro class PrintNames(NodeTransformer):
    def visit_Name(self, name):
        print("name: ", name.id)
        return name

macro def compute(foo: int, bar: int = 42):
    return foo * bar

macro FOO = compute(23, bar=12)

@PrintNames
def bar():
    x = 3
    print(x)
    print(FOO)

if __name__ == "__main__":
    bar()