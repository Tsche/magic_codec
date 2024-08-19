# coding: magic.incdec
i = 6

assert i-- == 6
assert i == 5
assert ++i == 6
assert --i == 5
assert i++ == 5
assert i == 6
assert (++i, 'i++') == (7, 'i++')
print("PASSED")
