# coding: magic.macro

macro_rules! print:
    | a=STRING { print($a) }
    | a=NUMBER { print(f"0x{$a:x}") }
    | a=atom   { print(f"{$a=}") }

FOO = 3
print!(FOO)
print!("x")
print!(3)
