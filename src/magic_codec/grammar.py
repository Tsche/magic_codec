# Pegen wrapper
# This is used to enable the @import meta for patch grammars

import argparse
from io import StringIO
import tokenize
from pegen.validator import validate_grammar
from pegen.build import build_parser

from pegen.python_generator import PythonParserGenerator
from pegen.tokenizer import Tokenizer
from pegen.grammar import Grammar
from pegen.grammar_parser import GeneratedParser as GrammarParser

# class GrammarParser(RawGrammarParser):
#     ...

def parse_grammar(
    grammar_file: str, verbose_tokenizer: bool = False, verbose_parser: bool = False
) -> Grammar:
    with open(grammar_file) as file:
        tokenizer = Tokenizer(tokenize.generate_tokens(file.readline), verbose=verbose_tokenizer)
        parser = GrammarParser(tokenizer, verbose=verbose_parser)
        grammar = parser.start()
        print(grammar)
        if not grammar:
            raise parser.make_syntax_error(grammar_file)

    return grammar

def generate_python(grammar):
    with StringIO() as file:
        gen = PythonParserGenerator(grammar, file)
        gen.generate("")
        return file.getvalue()

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
    grammar = parse_grammar(args.grammar_filename) 
    validate_grammar(grammar)
    if args.grammar:
        for line in str(grammar).splitlines():
            print(" ", line)
        return

    code = generate_python(grammar)
    if args.output is None:
        # print(code)
        return

    with open(args.output, 'w') as file:
        file.write(code)

if __name__ == "__main__":
    main()