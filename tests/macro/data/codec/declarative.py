# coding: magic.macro

macro_rules! print:
    | a=NUMBER { print(f"0x{$a:x}") }
    | a=STRING { 
    if True:
        print($a)
    }
    | a=atom   { print(f"{$a=}") }



FOO = 3
# print!(FOO)
# print!("x")
# print!(3)
