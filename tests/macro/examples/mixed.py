# coding: magic.macro

macro class PrintNames(NodeTransformer):
    def visit_Name(self, name):
        print("name: ", name.id)
        return name

@PrintNames
def bar():
    x = min(1, 2)
    print(x)

bar()
