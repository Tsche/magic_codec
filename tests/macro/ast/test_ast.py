import ast
import difflib
import pytest
from pathlib import Path

from magic_codec.macro import evaluator

DATA_DIR = Path(__file__).parent / "data"

def get_test_cases():
    py_files = sorted(DATA_DIR.rglob("*.py"))
    for py_file in py_files:
        ast_file = py_file.with_suffix(".ast")
        if ast_file.exists():
            test_id = str(py_file.relative_to(DATA_DIR))
            yield pytest.param(test_id, py_file, ast_file, id=test_id)

RESET = "\033[0m"
RED = "\033[31m"      # Deletion
GREEN = "\033[32m"    # Insertion

def colored_diff(a, b):
    diff = difflib.unified_diff(a.split('\n'), b.split('\n'), fromfile='expected', tofile='actual')
    def process_lines():
        for line in diff:
            if line.startswith('-'):
                yield f"{RED}{line}{RESET}"
            elif line.startswith('+'):
                yield f"{GREEN}{line}{RESET}"
            elif line.startswith(' '):
                yield line
    return '\n'.join(process_lines())


@pytest.mark.parametrize("name, py_path, ast_path", get_test_cases())
def test_ast_output(name, py_path: Path, ast_path: Path):
    tree = evaluator.parse(py_path.read_text(), py_path)
    actual_ast = ast.dump(tree, indent=2).rstrip()
    expected_ast = ast_path.read_text().rstrip()
    
    if actual_ast != expected_ast:
        # diff = ''.join(difflib.unified_diff(expected_ast, actual_ast, fromfile='expected', tofile='actual'))
        diff = colored_diff(expected_ast, actual_ast)
        pytest.fail(f"AST mismatch in {name}:{RESET}\nActual:\n{actual_ast}\nExpected:\n{actual_ast}\nDiff:\n{diff}")

if __name__ == "__main__":
    for param in get_test_cases():
        test_ast_output(*param.values)