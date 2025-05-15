import argparse
from pathlib import Path
from magic_codec.macros.evaluator import transform
from magic_codec.macros.macro_ast import unparse

def main():
    args_parser = argparse.ArgumentParser("magic_macro")
    args_parser.add_argument("source")
    args_parser.add_argument("--syntax-only", action="store_true")
    args_parser.add_argument("--preprocessor", action="store_true")
    args_parser.add_argument("--run", action="store_true")

    args = args_parser.parse_args()
    source, macro = transform(Path(args.source).read_text(), Path(args.source))
    if args.preprocessor:
        print("# =================== MACRO STATE  ===================")
        # print(ast.dump(interpreter.module, indent=4))
        print(unparse(macro))
    elif args.run:
        exec(unparse(source))
    else:
        print("# =================== PREPROCESSED ===================")
        # print(ast.dump(evaluated_tree, indent=4))
        print(unparse(source))

if __name__ == "__main__":
    main()