# Pegen wrapper
# This is used to enable the @import meta for patch grammars

import argparse
from io import StringIO
from pathlib import Path
import tokenize
from pegen.validator import validate_grammar
from pegen.python_generator import PythonParserGenerator
from pegen.tokenizer import Tokenizer
from pegen.grammar import Grammar
from pegen.grammar_parser import GeneratedParser as GrammarParser

from magic_codec.macros.evaluator import MacroEvaluator

# class GrammarParser(RawGrammarParser):
#     ...

def parse_grammar(
    grammar_file: str, verbose_tokenizer: bool = False, verbose_parser: bool = False
) -> Grammar:
    with open(grammar_file) as file:
        tokenizer = Tokenizer(tokenize.generate_tokens(file.readline), verbose=verbose_tokenizer)
        parser = GrammarParser(tokenizer, verbose=verbose_parser)
        grammar = parser.start()

        if not grammar:
            raise parser.make_syntax_error(grammar_file)

    return grammar

def generate_python(grammar):
    with StringIO() as file:
        gen = PythonParserGenerator(grammar, file)
        gen.generate("")
        return file.getvalue()

def expand_patch(grammar_path: Path, grammar: Grammar):
    grammar_folder = grammar_path.parent
    
    if not (parent := grammar.metas.get("import")):
        # cannot expand further
        return grammar
    parent: Path = Path(parent)
    if not parent.is_absolute():
        parent = grammar_folder / parent
    
    parent_grammar = parse_grammar(parent)
    expand_patch(parent, parent_grammar)

    # only take rules/metas from parent if they weren't overridden
    grammar.rules = parent_grammar.rules | grammar.rules
    grammar.metas = parent_grammar.metas | grammar.metas

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

    grammar = parse_grammar(args.grammar_filename)   
    if args.grammar and not args.full:
        print(grammar)
        return
    
    expand_patch(Path(args.grammar_filename), grammar)
    validate_grammar(grammar)
    
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