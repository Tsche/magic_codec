# coding: magic.macro

macro_rules! foo:
    | a=STRING : print($a)

foo!("x")
# print!(3)

# | a=NUMBER:
#         if $a > 3:
#             print(f"0x{$a:x}") 
#         else:
#             print("123")
#         print("")
