import subprocess
from urllib import request
from pathlib import Path
import shutil

SOURCE_URL = "https://raw.githubusercontent.com/we-like-parsers/pegen/refs/heads/main/data/python.gram"
GRAMMAR_PATH = Path(__file__).parent.parent / "src" / "magic_codec" / "macros" / "grammar" / "python.peg"
MACRO_GRAMMAR_PATH = Path(__file__).parent.parent / "src" / "magic_codec" / "macros" / "grammar" / "macro.peg"
MACRO_PATCH = Path(__file__).parent / "macro.patch"

def fetch_grammar():
    print("retrieving python grammar")
    request.urlretrieve(SOURCE_URL, GRAMMAR_PATH)

def make_macro_grammar():
    print("patching python grammar")
    shutil.copy(GRAMMAR_PATH, MACRO_GRAMMAR_PATH)
    subprocess.check_call(["patch", str(MACRO_GRAMMAR_PATH), str(MACRO_PATCH)])


if __name__ == "__main__":
    fetch_grammar()
    make_macro_grammar()