import argparse
import json
import sys
import tomllib
from pathlib import Path
from jsonschema import ValidationError, validate

def preprocess(data: str):
    return """
from magic_codec.builtin.toml import main

if __name__ == "__main__":
    main()
"""


def main():
    parser = argparse.ArgumentParser(
                    prog='magic.toml',
                    description='Verify toml data against json schemas')
    parser.add_argument('-s', '--schema', type=Path, required=True)      # option that takes a value
    args = parser.parse_args()

    data = tomllib.loads(Path(sys.argv[0]).read_text(encoding="utf-8"))
    schema = json.loads((Path(args.schema)).read_text(encoding="utf-8"))
    try:
        validate(data, schema)
    except ValidationError as exc:
        print(exc)
    else:
        print("Successfully validated.")
