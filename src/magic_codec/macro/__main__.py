import logging
import argparse
from pathlib import Path
from magic_codec.log import setup_logger
from magic_codec.macro.evaluator import transform
from magic_codec.macro.macro_ast import unparse
from magic_codec.isolation import Isolation


def run_isolated(source_path):
    with Isolation() as interp:
        interp.exec("""
from pathlib import Path
from magic_codec.macro.evaluator import transform
from magic_codec.macro.macro_ast import unparse
""")
        return interp.eval("unparse(transform(_code, Path(_path))[0])", {
            '_code': Path(source_path).read_text(),
            '_path': str(source_path)
        })


def main():
    args_parser = argparse.ArgumentParser("magic_macro")
    args_parser.add_argument("source")
    args_parser.add_argument('-v', '--verbose', action='count', default=0)
    args_parser.add_argument("--syntax-only", action="store_true")
    args_parser.add_argument("--preprocessor", action="store_true")
    args_parser.add_argument("--run", action="store_true")

    args = args_parser.parse_args()
    setup_logger(args.verbose)

    if args.run:
        source = run_isolated(args.source)
        exec(source)
        return

    source, macro = transform(Path(args.source).read_text(), Path(args.source))
    if args.preprocessor:
        # print(ast.dump(interpreter.module, indent=4))
        print(unparse(macro))
    else:
        # print(ast.dump(evaluated_tree, indent=4))
        print(unparse(source))


if __name__ == "__main__":
    main()
