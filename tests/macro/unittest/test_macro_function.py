import itertools
import pytest

decorator = ['@test', '@test(1)', '@test(1, foo=[x()])',
             '@test!', '@test!(1)', '@test!(1, foo=[x()])']

function_head = ["def foo():", "def foo(bar):", "def foo(oof, bar=baz()):",
                 "def foo() -> int:", "def foo(bar: int) -> int:", "def foo(bar: int = 2) -> int:",
                 "def foo[T](x: T) -> Optional[T]:", "def foo(x: Callable[[str, str], int]) -> Callable[[str, str], int]:"]

class_head = ["class Foo:", "class Foo(dict):", "class Foo[T]:", "class Foo[T](list):"]

body = ["\n    ...\n", " ...\n", "\n    if foo:\n        bar"]


def make_params(*args):
    return [''.join(combination) for combination in itertools.product(*args)]

@pytest.mark.parametrize('code', make_params(decorator))
def test_decorators(code):
    assert True

@pytest.mark.parametrize('code', make_params(function_head, body))
def test_functions(code):
    print(code)

@pytest.mark.parametrize('code', make_params(decorator, function_head, body))
def test_decorated_functions(code):
    assert True

@pytest.mark.parametrize('code', make_params(class_head, body))
def test_classes(code):
    assert True

@pytest.mark.parametrize('code', make_params(decorator, class_head, body))
def test_decorated_classes(code):
    assert True