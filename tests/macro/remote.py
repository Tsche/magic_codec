# coding: magic.macro
macro import ast

@macro
class LoadConstants(NodeTransformer):
    def __init__(self, constants: dict[str, str]):
        self.constants = {key: self.fetch(url) for key, url in constants.items()}

    @staticmethod
    def fetch(url: str):
        import urllib.request

        with urllib.request.urlopen(url) as handle:
            response = handle.read().decode(encoding="utf-8")
            result = ast.parse(response, mode="eval")
            if isinstance(result.body, ast.Name):
                return ast.Constant(result.body.id)
            return result.body

    def visit_Name(self, node: ast.Name):
        if node.id in self.constants:
            return self.constants[node.id]
        return node
    

@LoadConstants({
    'api_key': "https://gist.githubusercontent.com/Tsche/8c9ecffcf7e0f2f7c3fac338bc32a45b/raw/2d2f26612efb400cbf38d9afe1a1a281b50ea683/secret_key",
    'hash_fnc': "https://gist.githubusercontent.com/Tsche/3c3fbabfc13f22d994e343fca2a48023/raw/a8645539b25c9e024006225158d874cb40a0e97c/secret_function"
})
def main():
    print(api_key)
    print(hash_fnc(api_key))


if __name__ == "__main__":
    main()