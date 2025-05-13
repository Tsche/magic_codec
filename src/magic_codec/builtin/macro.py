import ast
from pathlib import Path
import re

# from magic_codec.legacy_macro import transform
# from magic_codec.util import untokenize

from magic_codec.macros.macro_ast import Code
from magic_codec.macros.evaluator import transform


def remove_magic(data: str) -> str:
    lines = data.splitlines()
    pattern = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)")
    for idx in range(2):
        if re.match(pattern, lines[idx]):
            lines[idx] = ""
    return "\n".join(lines)


def preprocess(data: str):
    import __main__
    source_path = None
    if __main__.__file__:
        source = Path(__main__.__file__).read_text(encoding="utf-8")
        if data == remove_magic(source):
            source_path = Path(__main__.__file__)
    code, _ = transform(data, source_path)
    return "\n\n" + Code(code).string + '\n'
