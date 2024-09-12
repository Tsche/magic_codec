from functools import cache
import functools
from io import StringIO
import itertools
import contextlib
from collections import deque, namedtuple
from tokenize import generate_tokens, untokenize
from types import EllipsisType
from typing import Deque, Iterable, Optional, Self, TypeVar
import ast as _ast

T = TypeVar("T")


class PeekableStream:
    def __init__(self, iterable: Iterable[T], max_cache_size: Optional[int] = None, default: Optional[T] = None):
        self.__iterator = iter(iterable)
        self.__cache: Deque[T] = deque([], maxlen=max_cache_size)
        self.__cursor: int = 0
        self.default: Optional[T] = default

    def __iter__(self):
        return self

    def __cache_next(self, advance_cursor=True):
        next_item = next(self.__iterator)
        self.__cache.append(next_item)
        if advance_cursor:
            self.__cursor = len(self.__cache)
        return next_item

    def __next__(self):
        # reset peek cursor
        self.__cursor = 0
        return self.__cache.popleft() if self.__cache else next(self.__iterator)

    def next(self):
        return next(self, self.default)

    def consume(self, n=None):
        return [self.next() for _ in range(n or 1)]

    def peek(self, n: Optional[int] = None):
        if n is not None:
            return self.peek_n(n)

        if self.__cursor < len(self.__cache):
            item = self.__cache[self.__cursor]
            self.__cursor += 1
            return item

        with contextlib.suppress(StopIteration):
            return self.__cache_next()

        return self.default

    def peek_n(self, n: int) -> list[T]:
        needed = n - (len(self.__cache) - self.__cursor)
        if needed > 0:
            self.__cache.extend(itertools.islice(self.__iterator, needed))

        items = list(itertools.islice(self.__cache, 
                                      self.__cursor, 
                                      self.__cursor + n))

        self.__cursor += len(self.__cache)
        needed = n - len(items)
        return items + [self.default for _ in range(needed)]

    def commit(self):
        self.__cache = deque(itertools.islice(self.__cache, self.__cursor, None), self.__cache.maxlen)
        self.__cursor = 0

    def rollback(self):
        self.__cursor = 0


Token = namedtuple("Token", ["type", "string"])
TokenQuery = tuple[int | EllipsisType, str | EllipsisType]

@cache
def get_tokens(data: str) -> list[Token]:
    return [Token(token.type, token.string) for token in list(generate_tokens(StringIO(data).readline))][:-1]


def eager(generator):
    @functools.wraps(generator)
    def evaluator(*argv, **kwargs):
        return list(generator(*argv, **kwargs))
    return evaluator


class TokenStream(PeekableStream):
    def __init__(self, iterable: Iterable[Token], max_cache_size: int | None = None):
        super().__init__(iterable, max_cache_size, Token(0, ''))

    def consume_if(self, needle: TokenQuery | list[TokenQuery]) -> Token | None:
        ...

    def consume_if_seq(self, needles: list[TokenQuery]) -> list[Token] | None:
        ...

    @eager
    def consume_while(self, conditional: callable) -> list[Token]:
        ...

    @eager
    def consume_until(self, value: TokenQuery) -> list[Token]:
        ...

    @eager
    def consume_line(self) -> list[Token]:
        yield None

    @eager
    def consume_balanced(self, increase: TokenQuery, decrease: TokenQuery) -> list[Token]:
        ...

    @eager
    def peek_while(self, conditional: callable) -> list[Token]:
        ...

    @eager
    def peek_until(self, value: TokenQuery) -> list[Token]:
        ...

    @eager
    def peek_line(self) -> list[Token]:
        yield None

    @eager
    def peek_balanced(self, increase: TokenQuery, decrease: TokenQuery) -> list[Token]:
        ...


class Code:
    __current_state: str | list[Token] | _ast.AST

    def __init__(self, state: str | list[Token] | _ast.AST | Self):
        self.__current_state = state.__current_state if isinstance(state, Code) else state
        if isinstance(self.__current_state, Iterable):
            # force conversion to Token in case a proc macro returned a plain tuple
            # also force evaluation of generators at this point
            self.__current_state = [Token(type_, string) for type_, string in self.__current_state]

    @property
    def string(self):
        if isinstance(self.__current_state, str):
            return self.__current_state
        elif isinstance(self.__current_state, _ast.AST):
            return _ast.unparse(self.__current_state)
        elif isinstance(self.__current_state, Iterable):
            return untokenize(self.__current_state)
        raise TypeError(f"Current state has invalid type {type(self.__current_state)}")

    @property
    def ast(self):
        if isinstance(self.__current_state, _ast.AST):
            return self.__current_state
        return _ast.parse(self.string)

    @property
    def tokens(self):
        if isinstance(self.__current_state, Iterable):
            return self.__current_state
        return get_tokens(self.string)
