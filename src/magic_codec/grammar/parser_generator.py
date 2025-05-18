from ast import Dict, List
from timeit import timeit
import token
from pegen.python_generator import MODULE_PREFIX, MODULE_SUFFIX
from pegen.grammar import GrammarVisitor, GrammarError
from pegen.parser_generator import RuleCheckingVisitor, compute_left_recursives, compute_nullables
from pegen.parser_generator import ParserGenerator as BaseParserGenerator
from copy import copy
from io import StringIO
from typing import IO, Optional, Text, Type
from pegen.python_generator import PythonParserGenerator, PythonCallMakerVisitor, InvalidNodeVisitor, UsedNamesVisitor
from pegen.grammar import Grammar, Rule, NamedItem, NameLeaf


class ParserGenerator(PythonParserGenerator):
    def __init__(self, grammar: Grammar, filename: IO[str] | None = None):
        super().__init__(grammar, filename)

    def start(self, filename: str):
        header = self.grammar.metas.get("header", MODULE_PREFIX)
        if header is not None:
            self.print(header.rstrip("\n").format(filename=filename))
        subheader = self.grammar.metas.get("subheader", "")
        if subheader:
            self.print(subheader)

        cls_name = self.grammar.metas.get("class", "GeneratedParser")
        base_name = self.grammar.metas.get("base", "Parser")
        additional_bases = self.grammar.metas.get("additional_bases", "")
        self.print(f"class {cls_name}({base_name}, {additional_bases}):")

        while self.todo:
            for rulename, rule in list(self.todo.items()):
                del self.todo[rulename]
                self.print()
                with self.indent():
                    self.visit(rule)

        self.print()
        with self.indent():
            self.write_class_vars()
        trailer = self.grammar.metas.get("trailer", MODULE_SUFFIX.format(class_name=cls_name))
        if trailer is not None:
            self.print(trailer.rstrip("\n"))

    def write_class_vars(self):
        self.print(f"KEYWORDS = {tuple(sorted(self.callmakervisitor.keywords))}")
        self.print(f"SOFT_KEYWORDS = {tuple(sorted(self.callmakervisitor.soft_keywords))}")
        self.print(f"RULES = ({', '.join(repr(k) for k in self.rules.keys())})")

    def generate(self, filename="") -> str:
        file = StringIO()
        self.file = file
        self.start(filename)
        self.file = None
        return file.getvalue()

class PatchRuleCheckingVisitor(GrammarVisitor):
    def __init__(self, rules: dict[str, Rule], tokens: set[str], parent_rules: list[str]):
        self.rules = rules
        self.parent_rules = parent_rules
        self.tokens = tokens

    def visit_NameLeaf(self, node: NameLeaf) -> None:
        if node.value not in self.rules and node.value not in self.tokens and node.value not in self.parent_rules:
            # TODO: Add line/col info to (leaf) nodes
            raise GrammarError(f"Dangling reference to rule {node.value!r}")

    def visit_NamedItem(self, node: NamedItem) -> None:
        if node.name and node.name.startswith("_"):
            raise GrammarError(f"Variable names cannot start with underscore: '{node.name}'")
        self.visit(node.item)

class PatchParserGenerator(ParserGenerator):
    def __init__(self, grammar: Grammar, parent: Type, tokens: set[str] = set(token.tok_name.values())):
        self.grammar = grammar
        self.parent = parent
        parent_rules = getattr(parent, "RULES", [])

        self.tokens = tokens
        self.rules = grammar.rules
        self.validate_rule_names()
        if "trailer" not in grammar.metas and "start" not in self.rules and "start" not in parent_rules:
            raise GrammarError("Grammar without a trailer must have a 'start' rule")
        
        checker = PatchRuleCheckingVisitor(self.rules, self.tokens, parent_rules)
        for rule in self.rules.values():
            checker.visit(rule)

        self.file = None
        self.level = 0
        compute_nullables(self.rules)
        self.first_graph, self.first_sccs = compute_left_recursives(self.rules)
        self.todo = self.rules.copy()  # Rules to generate
        self.counter = 1000  # For name_rule()/name_loop()
        self.all_rules: dict[str, Rule] = {}  # Rules + temporal rules
        self._local_variable_stack: list[list[str]] = []

        tokens.add("SOFT_KEYWORD")
        tokens.update(
            ["FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"]
        )  # used in metagrammar to support Python 3.12 f-strings; don't exist in 3.11

        self.callmakervisitor: PythonCallMakerVisitor = PythonCallMakerVisitor(self)
        self.invalidvisitor: InvalidNodeVisitor = InvalidNodeVisitor()
        self.usednamesvisitor: UsedNamesVisitor = UsedNamesVisitor()
        self.unreachable_formatting = "None  # pragma: no cover"
        self.location_formatting = ("lineno=start_lineno, col_offset=start_col_offset, "
                                    "end_lineno=end_lineno, end_col_offset=end_col_offset")
        self.cleanup_statements: list[str] = []

    def write_class_vars(self):
        base_name = self.parent.__name__
        self.print(f"KEYWORDS = tuple(set([*{tuple(sorted(self.callmakervisitor.keywords))}, *getattr({base_name}, 'KEYWORDS', [])]))")
        self.print(f"SOFT_KEYWORDS = tuple(set([*{tuple(sorted(self.callmakervisitor.soft_keywords))}, *getattr({base_name}, 'SOFT_KEYWORDS', [])]))")
        self.print(f"RULES = tuple(set([{', '.join(repr(k) for k in self.rules.keys())}, *getattr({base_name}, 'KEYWORDS', [])]))")
