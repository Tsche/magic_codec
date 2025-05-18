# Pegen wrapper
# This is used to enable the @import meta for patch grammars

import argparse
import importlib.util
from pathlib import Path

from magic_codec.grammar import generate_python, parse_grammar_file, Grammar
from magic_codec.grammar.parser_generator import ParserGenerator, PatchParserGenerator

def get_parent(grammar_path: Path, grammar: Grammar):   
    if not (parent := grammar.metas.get("extends")) or not (base := grammar.metas.get("base")):
        # cannot expand further
        return None
    
    module_path = Path(grammar_path.parent / parent)
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, base)


def main():
    argparser = argparse.ArgumentParser(prog="pegen", description="Experimental PEG-like parser generator")
    argparser.add_argument("grammar_filename", help="Grammar description")
    argparser.add_argument(
        "-o",
        "--output",
        metavar="OUT",
        default=None,
        help="Where to write the generated parser. Prints to stdout if not set.",
    )
    argparser.add_argument('-g', '--grammar', action='store_true', help="Print clean grammar and exit.")
    args = argparser.parse_args()

    grammar = parse_grammar_file(args.grammar_filename)   
    if args.grammar:
        print(grammar)
        return
    
    if parent := get_parent(Path(args.grammar_filename), grammar):
        code = PatchParserGenerator(grammar, parent).generate(args.grammar_filename)
    else:
        code = ParserGenerator(grammar).generate(args.grammar_filename)

    if args.output is None:
        print(code)
        return

    with open(args.output, 'w') as file:
        file.write(code)

if __name__ == "__main__":
    main()