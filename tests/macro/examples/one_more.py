# coding: magic.macro
macro import ast

macro class TransformInt(NodeTransformer):
    def visit_Num(self, node):
        if isinstance(node.n, int):
            return ast.BinOp(
                left=node,
                op=ast.Add(),
                right=ast.Constant(1)
            )
        return node

@TransformInt
def foo(a, b):
    return (a - 2) * (b + 2.5)

if __name__ == "__main__":
    print(foo(1, 2))
