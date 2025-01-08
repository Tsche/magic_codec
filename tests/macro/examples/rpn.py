# coding: magic.macro
from! magic_codec.util import TokenStream, Token, untokenize
from! token import NUMBER, OP

def pn!(tokens):
  stream = TokenStream(tokens.tokens)
  stack = []

  def parse_expr():
    first_operand  = stream.maybe((NUMBER, ...)) or Token(NUMBER, stack.pop())
    second_operand = stream.maybe((NUMBER, ...)) or Token(NUMBER, stack.pop())
    operator       = stream.expect((OP, ...))

    expression = untokenize([first_operand, operator, second_operand])
    result     = eval(expression)
    stack.append(result)

  parse_expr()
  while len(stack) > 1 and stream.peek().type in (NUMBER, OP):
    parse_expr()
  return stack.pop()

print(pn!(3 4 + 6 +))