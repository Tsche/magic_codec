from collections import namedtuple
import sys
from token import DEDENT, INDENT, NAME, NEWLINE, NL, NUMBER, OP, STRING
from tokenize import TokenInfo, untokenize
from pegen.grammar import GrammarVisitor, Alt
from pegen.tokenizer import Tokenizer

from magic_codec.macro.code import Code, Token
from magic_codec.grammar import parse_grammar
from magic_codec.grammar.parser_generator import PatchParserGenerator
from magic_codec.parser.macro_peg import MacroPegParser
from magic_codec.parser.python import PythonParser

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
                            (OP, '*'), (NAME, '_Code'), (OP, '('), (NAME, next.string), (OP, ')'), (OP, '.'), (NAME, 'tokens'), 
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
        print("!!", (node.action))
        node.action = untokenize(quote_tokens(Code(node.action)))


def make_parser(name: str, rules: list):
    rules = [Token(t.type, t.string) if isinstance(t, TokenInfo) else Token(t[0], t[1]) for t in rules]
    if rules[-1].type == 0:
        rules = rules[:-1]

    if len(rules) >= 2 and rules[0].type not in (NL, NEWLINE) and rules[1].type != INDENT:
        rules = [Token(INDENT, '  '), *rules, Token(DEDENT, '')]
    
    tokens = [
        Token(1, name), Token(55, ':'), Token(4, '\n'),
        *rules,
        Token(0, '')]

    tokenizer = Tokenizer(iter(rules))
    parser = MacroPegParser(tokenizer)
    grammar = parser.start()
    print(grammar)
    sys.exit()
    
    # assert grammar

    # ActionTokenizer().visit(grammar)

#     grammar.metas["header"] = """
# import ast
# import sys
# import tokenize
# from typing import Any, Optional
# from pegen.parser import memoize, memoize_left_rec, logger
# from magic_codec.parser.python import PythonParser
# """
#     grammar.metas["trailer"] = ""
#     grammar.metas["class"] = f"_{name}_Parser"
#     grammar.metas["base"] = "PythonParser"

#     generator = PatchParserGenerator(grammar, PythonParser)
#     return generator.generate()


def to_tokenizer(code: Code):
    from pegen.tokenizer import Tokenizer
    tokens = list(code.tokens)
    tokens = [Token(t.type, t.string) if isinstance(t, TokenInfo) else Token(t[0], t[1]) for t in tokens]
    return Tokenizer(iter(tokens))