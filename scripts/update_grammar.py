import subprocess
from urllib import request
from pathlib import Path
import shutil

SOURCE_URL = "https://raw.githubusercontent.com/we-like-parsers/pegen/refs/heads/main/data/python.gram"
GRAMMAR_PATH = Path(__file__).parent.parent / "src" / "magic_codec" / "grammar" / "python.peg"
GRAMMAR_PATCH = Path(__file__).parent / "python.patch"

def fetch_grammar():
    print("retrieving python grammar")
    request.urlretrieve(SOURCE_URL, GRAMMAR_PATH)

def patch_grammar():
    print("patching python grammar")
    subprocess.check_call(["patch", str(GRAMMAR_PATH), str(GRAMMAR_PATCH)])


if __name__ == "__main__":
    fetch_grammar()
    patch_grammar()