from io import StringIO
import sys
import traceback
from pegen.tokenizer import Tokenizer
from pegen.grammar import Grammar
from pegen.grammar_parser import GeneratedParser as GrammarParser
from pegen.validator import validate_grammar
import tokenize
from typing import Iterable
from pegen.tokenizer import Tokenizer
from .parser_generator import ParserGenerator

def parse_grammar(tokens: Iterable, grammar_file = "<unknown>", verbose=False) -> Grammar:
    tokenizer = Tokenizer(iter(tokens))
    parser = GrammarParser(tokenizer, verbose=verbose)
    grammar = parser.start()
    if not grammar:
        err = parser.make_syntax_error(grammar_file)
        traceback.print_exception(err.__class__, err, None)
        sys.exit(1)

    validate_grammar(grammar)
    return grammar

def parse_grammar_file(grammar_file: str) -> Grammar:
    with open(grammar_file) as file:
        return parse_grammar(tokenize.generate_tokens(file.readline), grammar_file)

def parse_grammar_str(grammar: str, verbose=False):
    return parse_grammar(tokenize.generate_tokens(StringIO(grammar).readline))

def generate_python(grammar):
    gen = ParserGenerator(grammar)    
    return gen.generate("")

# def expand_patch(grammar_path: Path, grammar: Grammar):
#     grammar_folder = grammar_path.parent
    
#     if not (parent := grammar.metas.get("import")):
#         # cannot expand further
#         return grammar
    
#     parent: Path = Path(parent)
#     assert isinstance(parent, Path)
    
#     if not parent.is_absolute():
#         parent = grammar_folder / parent
    
#     parent_grammar = parse_grammar_file(parent)
#     expand_patch(parent, parent_grammar)

#     # only take rules/metas from parent if they weren't overridden
#     grammar.rules = parent_grammar.rules | grammar.rules
#     grammar.metas = parent_grammar.metas | grammar.metas
