# magic codec - preprocessing for the python interpreter

magic_codec is a small utility to make writng preprocessors for Python easier. This uses a custom codec to kick off preprocessing before passing the result to the Python interpreter. You can find a more in-depth explanation of how this works over at [pydong.org](https://pydong.org)

## Loading builtins
Currently the following preprocessors are available:
- [braces](src/magic_codec/builtin/braces.py) Python with braces - inspired by Bython (ie. `python tests/braces/test.by`)
- [incdec](src/magic_codec/builtin/incdec.py) Extends python with unary prefix `++i` and postfix `i++` increment/decrement expressions (ie. `python tests/incdec/incdec.py`)
- [cpp](src/magic_codec/builtin/cpp.py) lets the Python interpreter interpret C++ via cppyy (ie. `python tests/test.cpp`)
- [toml](src/magic_codec/builtin/toml.py) validate toml files using json schemas (ie. `python tests/toml/data_valid.toml -s tests/toml/schema.json`)

Builtins can be loaded by setting the codec to `magic.builtin_name` where `builtin_name` is the name of the builtin.

## Loading extensions
To extend magic_codec with your own preprocessors, you can create another Python package whose name is prefixed with `magic_`. Setting the codec to `magic_foo` would load the `magic_foo` package and check if it has a function `preprocess`.

The expected signature of `preprocess` is as follows:
```py
def preprocess(data: str) -> str:
    raise NotImplementedError
```
