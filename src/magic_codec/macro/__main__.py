import ast
import logging
import argparse
from pathlib import Path
from magic_codec.log import setup_logger
from magic_codec.macro import evaluator
from magic_codec.macro.macro_ast import unparse
from magic_codec.isolation import Isolation


def run_isolated(source: str, source_file: Path):
    with Isolation() as interp:
        interp.exec("""
from pathlib import Path
from magic_codec.macro.evaluator import transform
from magic_codec.macro.macro_ast import unparse
""")
        return interp.eval("unparse(transform(_code, Path(_path))[0])", {
            '_code': source,
            '_path': str(source_file)
        })


def main():
    args_parser = argparse.ArgumentParser("magic_macro")
    args_parser.add_argument("source")
    args_parser.add_argument('-v', "--verbose", action="count", default=0)
    args_parser.add_argument('-t', "--tree", action="store_true")
    args_parser.add_argument('-s', "--syntax-only", action="store_true")
    args_parser.add_argument('-p', "--preprocessor", action="store_true")
    args_parser.add_argument('-r', "--run", action="store_true")

    args = args_parser.parse_args()
    setup_logger(args.verbose)
    source = Path(args.source).read_text()
    source_file = Path(args.source)
    
    if args.run:
        exec(run_isolated(source, source_file))
        return

    if args.syntax_only:       
        tree = evaluator.parse(source, source_file)
        if args.tree:
            print(ast.dump(tree, indent=2))
        else:
            # todo implement unparser for syntax highlighting
            print("unimplemented")
            # print(unparse(tree))
        return

    source, macro = evaluator.transform(source, source_file)
    if args.preprocessor:
        if args.tree:
            print(ast.dump(macro, indent=2))
        else:
            print(unparse(macro))
    else:
        if args.tree:
            print(ast.dump(source, indent=2))
        else:
            print(unparse(source))


if __name__ == "__main__":
    main()
