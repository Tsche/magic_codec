# coding: magic.macro

macro_rules! print:
    (a=STRING): print($a)
    (a=NUMBER):
        if $a > 3:
            print(f"0x{$a:x}") 
        else:
            print("123")


print!("x")
print!(3)
