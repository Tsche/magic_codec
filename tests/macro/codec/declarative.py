
@macro
def inject(code):
    return code

@macro
def macro_rules(body, name = None):
    print(body)
    print("foo")

macro_rules! pretty_print:
    | a=NUMBER { print(f"0x{$a:x}") }
    | a=STRING { print($a) }
    | a=NAME { print(f"{$a=}") }
    | a=atom { print($a) }

x = 3
pretty_print!(x) # prints "x=3"
pretty_print!(24) # prints "0x18"