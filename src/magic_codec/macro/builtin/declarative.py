from collections import namedtuple
import sys
from token import DEDENT, INDENT, NAME, NEWLINE, NL, NUMBER, OP, STRING
from tokenize import TokenInfo, untokenize
from pegen.grammar import GrammarVisitor, Alt
from pegen.tokenizer import Tokenizer

from magic_codec.macro.code import Code, Token
from magic_codec.grammar.parser_generator import PatchParserGenerator
from magic_codec.parser.peg import PegParser
from magic_codec.parser.python import PythonParser

# TODO drop
from magic_codec.parser.macro_peg import MacroPegParser

# def quote_tokens(action: Fragment):
#     # This could instead be done by introducing replacements in peg's action grammar
#     # TODO decide whether to do this token or tree based
    
#     tokenizer = Tokenizer(action.data)
#     yield from [(OP, '['), (OP, '*'), (OP, '[')]
#     try:
#         while (tok := tokenizer.getnext()):
#             if tok.type == OP and tok.string == '$':
#                 next = tokenizer.peek()
#                 if next.type != NAME:
#                     print(tok, next)
#                     raise RuntimeError("Invalid token stream")
#                 tokenizer.getnext()
#                 yield from [(OP, ']'), (OP, ','), 
#                             (OP, '*'), (NAME, '_Code'), (OP, '('), (NAME, next.string), (OP, ')'), (OP, '.'), (NAME, 'tokens'), 
#                             (OP, ','), (OP, '*'), (OP, '[')]
#                 continue

#             yield from [(OP, '('), (NUMBER, str(tok.type)), (OP, ','), (STRING, repr(tok.string)), (OP, ')'), (OP, ',')]
#     except StopIteration:
#         pass
#     finally:
#         yield (OP, ']')
#         yield (OP, ']')


# class ActionTokenizer(GrammarVisitor):
#     def visit_Replacement(self, node: Replacement):
#         print("replacement")
#         ...

#     def visit_Token(self, node: Token):
#         print("token")
#         print(node._sloc)
#         ...

#     def visit_Fragment(self, node: Fragment):
#         for token in node.data:
#             self.visit(token)
#             # print(type(token))
#             # if isinstance(token, Fragment):
#             #     self.visit_Fragment(token)

#     def visit_Alt(self, node: Alt):
#         if not node.action:
#             return
#         self.visit(node.action)
#         sys.exit(0)
#         # node.action = untokenize(quote_tokens(node.action))


def make_parser(name: str, rules: Code):
    out_rules = [Token(t) for t in rules.tokens]
    if out_rules[-1].type == 0:
        out_rules = out_rules[:-1]

    if len(out_rules) >= 2 and out_rules[0].type not in (NL, NEWLINE) and out_rules[1].type != INDENT:
        out_rules = [Token(INDENT, '  '), *out_rules, Token(DEDENT, '')]
    
    tokens = [
        Token(1, name), Token(55, ':'), Token(4, '\n'),
        *out_rules,
        Token(0, '')]
    print(tokens)
    tokenizer = Tokenizer(iter(tokens))
    parser = MacroPegParser(tokenizer, verbose=False)
    grammar = parser.start()
    assert grammar
    print("GRAMMAR VERIFIED")
    # ActionTokenizer().visit(grammar)

    grammar.metas["header"] = """
import ast
import sys
import tokenize
from typing import Any, Optional
from pegen.parser import memoize, memoize_left_rec, logger
from magic_codec.parser.python import PythonParser
"""
    grammar.metas["trailer"] = ""
    grammar.metas["class"] = f"_{name}_Parser"
    grammar.metas["base"] = "PythonParser"

    generator = PatchParserGenerator(grammar, PythonParser)
    return generator.generate()


def to_tokenizer(code: Code):
    from pegen.tokenizer import Tokenizer
    tokens = list(code.tokens)
    tokens = [Token(t.type, t.string) if isinstance(t, TokenInfo) else Token(t[0], t[1]) for t in tokens]
    return Tokenizer(iter(tokens))