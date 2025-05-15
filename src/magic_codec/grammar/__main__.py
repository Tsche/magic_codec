# Pegen wrapper
# This is used to enable the @import meta for patch grammars

import argparse
from pathlib import Path

from magic_codec.grammar import expand_patch, generate_python, parse_grammar_file

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
    argparser.add_argument('-f', '--full', action='store_true', help="Expand patch grammars before printing.")
    args = argparser.parse_args()

    grammar = parse_grammar_file(args.grammar_filename)   
    if args.grammar and not args.full:
        print(grammar)
        return
    
    expand_patch(Path(args.grammar_filename), grammar)
    
    if args.grammar:
        print(grammar)
        return

    code = generate_python(grammar)
    if args.output is None:
        print(code)
        return

    with open(args.output, 'w') as file:
        file.write(code)

if __name__ == "__main__":
    main()