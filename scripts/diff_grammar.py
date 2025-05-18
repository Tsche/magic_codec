import difflib
from magic_codec.grammar import parse_grammar_file
from pathlib import Path

grammar_dir = Path(__file__).parent.parent / 'src' / 'magic_codec' / 'grammar'

cpython = parse_grammar_file(str(grammar_dir / 'cpython.peg'))
python = parse_grammar_file(str(grammar_dir / 'python.peg'))

RESET = "\033[0m"
RED = "\033[31m"      # Deletion
GREEN = "\033[32m"    # Insertion

def colored_diff(a, b):
    diff = difflib.unified_diff(a.split('\n'), b.split('\n'))
    for line in diff:
        if line.startswith('-'):
            print(f"{RED}{line}{RESET}")
        elif line.startswith('+'):
            print(f"{GREEN}{line}{RESET}")
        elif line.startswith(' '):
            print(line)

for key, value in cpython.rules.items():
    if key not in python.rules:
        print(f"Rule {key} missing")
        continue
    if str(value) != (cvalue := str(python.rules[key])):
        colored_diff(str(cvalue), str(value))