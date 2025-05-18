# coding: magic.macro

@macro
def macro_rules(unparsed_name):
    # parse name, ensure it is a valid Python identifier
    name = unparsed_name.to("name").string
    def parse_rules(rules):
        from magic_codec.macro.declarative import make_parser
        parser = make_parser(name, rules.tokens)
        __make_macro(_CodeArtifact(parser))
        __make_macro(_CodeArtifact(f"""
def {name}(code):
    from magic_codec.macro.declarative import to_tokenizer
    try:
        return _CodeArtifact(_{name}_Parser(to_tokenizer(code)).{name}())
    except StopIteration:
        raise RuntimeError(f"Invalid declarative macro use: {name}!({{code.string}})")
"""))
    return parse_rules


macro_rules! print:
    | a=STRING { print($a); }
    | a=NUMBER { print(f"0x{$a:x}") }
    | a=atom { print(f"{$a=}") }

FOO = 3
print!(FOO)
print!("x")
print!(3)
