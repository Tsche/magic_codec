from collections import namedtuple
from pathlib import Path
from token import DEDENT, ENDMARKER, INDENT, NAME, NEWLINE, NL, NUMBER, OP, STRING
from tokenize import TokenInfo, untokenize
from typing import Iterable
from pegen.grammar import GrammarVisitor, Alt, NamedItem
from pegen.tokenizer import Tokenizer

from magic_codec.macros.macro_ast import Code
from magic_codec.grammar import parse_grammar, parse_grammar_file
from magic_codec.grammar.parser_generator import ParserGenerator, PatchParserGenerator
from magic_codec.macros.macro_parser import MacroPythonParser


class Token(namedtuple("Token", ["type", "string"])):
    start: tuple[int, int]
    end: tuple[int, int]
    line: str

    def __new__(cls, type: int, string: str):
        obj = super().__new__(cls, type, string)
        obj.start = (0, 0)
        obj.end = (0, 1)
        obj.line = ""
        return obj


def quote_tokens(action: Code):
    tokenizer = Tokenizer(iter(action.tokens))
    yield from [(OP, '['), (OP, '*'), (OP, '[')]
    try:
        while (tok := tokenizer.getnext()):
            if tok.type == OP and tok.string == '$':
                next = tokenizer.peek()
                if next.type != NAME:
                    print(tok, next)
                    raise RuntimeError("Invalid token stream")
                tokenizer.getnext()
                yield from [(OP, ']'), (OP, ','), 
                            (OP, '*'), (NAME, '_CodeArtifact'), (OP, '('), (NAME, next.string), (OP, ')'), (OP, '.'), (NAME, 'tokens'), 
                            (OP, ','), (OP, '*'), (OP, '[')]
                continue

            yield from [(OP, '('), (NUMBER, str(tok.type)), (OP, ','), (STRING, repr(tok.string)), (OP, ')'), (OP, ',')]
    except StopIteration:
        pass
    finally:
        yield (OP, ']')
        yield (OP, ']')


class ActionTokenizer(GrammarVisitor):
    def visit_Alt(self, node: Alt):
        if not node.action:
            return

        tokens = list(quote_tokens(Code(node.action)))
        # print(untokenize(tokens))
        node.action = untokenize(tokens)


def make_parser(name: str, rules: list):
    rules = [Token(t.type, t.string) if isinstance(t, TokenInfo) else Token(t[0], t[1]) for t in rules]
    if rules[-1].type == 0:
        rules = rules[:-1]

    if len(rules) >= 2 and not (rules[0].type in (NL, NEWLINE) and rules[1].type == INDENT):
        rules = [Token(INDENT, '  '), *rules, Token(DEDENT, '')]
    
    tokens = [
        Token(1, name), Token(55, ':'), Token(4, '\n'),
        *rules,
        Token(0, '')]
    grammar = parse_grammar(iter(tokens))

    ActionTokenizer().visit(grammar)

    grammar.metas["header"] = """
import ast
import sys
import tokenize
from typing import Any, Optional
from pegen.parser import memoize, memoize_left_rec, logger
from magic_codec.grammar.python_parser import PythonParser
"""
    grammar.metas["trailer"] = ""
    grammar.metas["class"] = f"_{name}_Parser (PythonParser): # "


    base_grammar_file = Path(__file__).parent.parent / 'grammar' / 'python.peg'
    base_grammar = parse_grammar_file(str(base_grammar_file))

    generator = PatchParserGenerator(grammar, base_grammar)
    return generator.generate()


def to_tokenizer(code: Code):
    from pegen.tokenizer import Tokenizer
    tokens = list(code.tokens)
    tokens = [Token(t.type, t.string) if isinstance(t, TokenInfo) else Token(t[0], t[1]) for t in tokens]
    return Tokenizer(iter(tokens))