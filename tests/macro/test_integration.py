import ast
import difflib
import pytest
from pathlib import Path

from magic_codec.macro import evaluator


def get_test_cases(data_dir: Path, input_pattern: str, expected_suffix: str):
    files = sorted(data_dir.rglob(input_pattern))
    for input_file in files:
        expected_file = input_file.with_suffix(expected_suffix)
        if expected_file.exists():
            test_id = str(input_file.relative_to(data_dir))
            yield pytest.param(test_id, input_file, expected_file, id=test_id)
        else:
            print(f"Missing test result {expected_file}")


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


DATA_DIR = Path(__file__).parent / "data"

AST_CASES = get_test_cases(DATA_DIR / "ast", "*.py", ".ast")
CODEC_CASES = get_test_cases(DATA_DIR / "codec", "*.py", ".out.py")


@pytest.mark.parametrize("name, py_path, ast_path", AST_CASES)
def test_ast_output(name, py_path: Path, ast_path: Path):
    tree = evaluator.parse(py_path.read_text(), py_path)
    actual_ast = ast.dump(tree, indent=2).rstrip()
    expected_ast = ast_path.read_text().rstrip()

    if actual_ast != expected_ast:
        diff = colored_diff(expected_ast, actual_ast)
        pytest.fail(f"AST mismatch in {name}:{RESET}\nActual:\n{actual_ast}\nExpected:\n{actual_ast}\nDiff:\n{diff}")

@pytest.mark.parametrize("name, py_path, expected_path", CODEC_CASES)
def test_codec(name, py_path: Path, expected_path: Path):
    actual = py_path.read_text(encoding="magic.macro").strip()
    expected = expected_path.read_text().strip()
    
    if actual != expected:
        diff = colored_diff(expected, actual)
        pytest.fail(f"Code mismatch in {name}:{RESET}\nActual:\n{actual}\nExpected:\n{expected}\nDiff:\n{diff}")


if __name__ == "__main__":
    for param in AST_CASES:
        test_ast_output(*param.values)

    for param in CODEC_CASES:
        test_codec(*param.values)
