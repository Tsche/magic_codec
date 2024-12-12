import sys
from pathlib import Path
from magic_codec.builtin.macro import Context, parse_macro
from magic_codec.util import TokenStream, get_tokens

if __name__ == "__main__":
  path = Path.cwd() / sys.argv[1]
  # print("before: ")
  # print(path.read_text(encoding="utf-8"))
  # print("after: ")
  print(path.read_text(encoding="magic.macro"))
