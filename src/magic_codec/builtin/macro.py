from pathlib import Path
import re

from magic_codec.macro import transform
from magic_codec.util import untokenize


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
    _, code = transform(data, source_path=source_path)
    return untokenize(code)
