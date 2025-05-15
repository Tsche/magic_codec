from copy import copy
from io import StringIO
from typing import IO, Optional, Text
from pegen.python_generator import PythonParserGenerator
from pegen.grammar import Grammar, Rule

class ParserGenerator(PythonParserGenerator):
    def __init__(self, grammar: Grammar):
        super().__init__(grammar, None)
    
    def generate(self) -> str:
        file = StringIO()
        self.file = file
        super().generate("")
        self.file = None
        return file.getvalue()
    

class PatchParserGenerator(PythonParserGenerator):
    def __init__(self, grammar: Grammar, base_grammar: Grammar):
        full_grammar = copy(grammar)
        full_grammar.rules = base_grammar.rules | grammar.rules

        super().__init__(full_grammar, None)
        
        # bump counter to avoid conflicts
        self.counter += 1000
        
        self.todo = grammar.rules
    
    def generate(self) -> str:
        file = StringIO()
        self.file = file
        super().generate("")
        self.file = None
        return file.getvalue()
