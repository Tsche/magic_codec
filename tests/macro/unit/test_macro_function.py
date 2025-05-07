# import itertools

# from magic_codec.builtin.macro import parse_decorators
# from magic_codec.util import tokenize, TokenStream
# # import pytest

# decorators = ["@test", "@test(1)", "@test(1, foo=[x()])",
#              "@test!", "@test!(1)", "@test!(1, foo=[x()])",
#              "@foo.bar", "@foo!.bar", "@foo!.bar!",
#              "@foo.bar(1)", "@foo(1).bar", "@foo(1).bar(2)",
#              "@foo!.bar(1)", "@foo!(1).bar", "@foo!(1).bar(2)",
#              "@foo!.bar!(1)", "@foo!(1).bar!", "@foo!(1).bar!(2)",
#              ]

# function_heads = ["def foo():", "def foo(bar):", "def foo(oof, bar=baz()):",
#                  "def foo() -> int:", "def foo(bar: int) -> int:", "def foo(bar: int = 2) -> int:",
#                  "def foo[T](x: T) -> Optional[T]:", "def foo(x: Callable[[str, str], int]) -> Callable[[str, str], int]:"]
# function_heads_bang = [signature.replace("foo", "foo!") for signature in function_heads]
# function_heads_macro = [f"macro {signature}" for signature in function_heads]
# function_heads_async = [f"async {signature}" for signature in function_heads]

# # order doesn"t matter for soft keywords
# function_heads_async_macro = [f"async macro {signature}" for signature in function_heads] \
#     + [f"macro async {signature}" for signature in function_heads]

# class_head = ["class Foo:", "class Foo(dict):", "class Foo[T]:", "class Foo[T](list):"]
# class_head_bang = [head.replace("Foo", "Foo!") for head in class_head]
# class_head_macro = [f"macro {head}" for head in class_head]

# body = ["\n    ...\n", " ...\n", "\n    if foo:\n        bar"]


# def make_params(*args):
#     return ["".join(combination) for combination in itertools.product(*args)]

# # @pytest.mark.parametrize("code", make_params(decorators))
# # def test_decorators(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(function_heads, body))
# # def test_functions(code):
# #     print(code)

# # @pytest.mark.parametrize("code", make_params(function_heads_bang, body))
# # def test_bang_functions(code):
# #     ...

# # @pytest.mark.parametrize("code", make_params(decorators, function_heads, body))
# # def test_decorated_functions(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(decorators, function_heads_bang, body))
# # def test_decorated_bang_functions(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(decorators, function_heads_async, body))
# # def test_decorated_async_functions(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(decorators, function_heads_macro, body))
# # def test_decorated_macro_functions(code):
# #     assert True

# # @pytest.mark.parametrize("code", [*make_params(decorators, function_heads_async_macro, body),
# #                                   *make_params(decorators, function_head_macro_async, body)])
# # def test_decorated_async_macro_functions(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(class_head, body))
# # def test_classes(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(decorators, class_head, body))
# # def test_decorated_classes(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(class_head_bang, body))
# # def test_bang_classes(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(decorators, class_head_bang, body))
# # def test_decorated_bang_classes(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(class_head_macro, body))
# # def test_macro_classes(code):
# #     assert True

# # @pytest.mark.parametrize("code", make_params(decorators, class_head_macro, body))
# # def test_decorated_macro_classes(code):
# #     assert True

# def test_decorators():
#     for decorator in decorators:
#         tokens = list(tokenize(decorator))
#         parsed = parse_decorators(TokenStream(tokens))
#         assert len(parsed) == 1, "More than one decorator detected"

#         print(parsed[0].to_tokens())
#         print(tokens)
#         print()
#         # print(parsed[0].to_tokens() == tokens)

# if __name__ == "__main__":
#     test_decorators()
