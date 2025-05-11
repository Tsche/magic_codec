import argparse
from pathlib import Path
from magic_codec.macros.evaluator import transform

def main():
    args_parser = argparse.ArgumentParser("magic_macro")
    args_parser.add_argument("source")
    args_parser.add_argument("--syntax-only", action="store_true")
    args_parser.add_argument("--preprocessor", action="store_true")
    args_parser.add_argument("--run", action="store_true")

    args = args_parser.parse_args()
    source, macro = transform(Path(args.source).read_text(), Path(args.source))


if __name__ == "__main__":
    main()