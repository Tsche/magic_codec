import ast
import difflib
import pytest
from pathlib import Path

from magic_codec.macro import evaluator

DATA_DIR = Path(__file__).parent / "data"

def get_test_cases():
    py_files = sorted(DATA_DIR.rglob("*.py"))
    for py_file in py_files:
        if len(py_file.suffixes) != 1:
            continue

        result_file = py_file.with_suffix(".out.py")
        if result_file.exists():
            test_id = str(py_file.relative_to(DATA_DIR))
            yield pytest.param(test_id, py_file, result_file, id=test_id)
        else:
            print(f"Missing test result {result_file}")

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

from pathlib import Path

@pytest.mark.parametrize("name, py_path, expected_path", get_test_cases())
def test_codec(name, py_path: Path, expected_path: Path):
    actual = py_path.read_text(encoding="magic.macro").strip()
    expected = expected_path.read_text().strip()
    
    if actual != expected:
        diff = colored_diff(expected, actual)
        pytest.fail(f"Code mismatch in {name}:{RESET}\nActual:\n{actual}\nExpected:\n{actual}\nDiff:\n{diff}")

if __name__ == "__main__":
    for param in get_test_cases():
        test_codec(*param.values)