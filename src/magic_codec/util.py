from dataclasses import dataclass
from functools import cache
import functools
from io import StringIO
import itertools
import contextlib
from collections import deque, namedtuple
import re
from tokenize import generate_tokens
from types import EllipsisType
from typing import Any, Deque, Iterable, Iterator, Optional, Self, TypeVar, Callable, get_type_hints
import ast as _ast
import token

from colorama import Back, Fore, Style


def force_conversion(to: type | Callable | None = None):
    def wrapper(generator):
        target = (to if isinstance(to, type)
                  else get_type_hints(generator or object).get('return'))
        assert target, "Could not figure out what to convert to"

        @functools.wraps(generator)
        def convert(*argv, **kwargs):
            return target(generator(*argv, **kwargs))
        return convert

    if to is None or isinstance(to, type):
        # ie. force_conversion() or force_conversion(to=list)
        return wrapper
    # ie. force_conversion
    return wrapper(to)


def decorated(message: Any, fg: Optional[Fore] = None, bg: Optional[Back] = None, style: Optional[Style] = None,):
    if not isinstance(message, str):
        message = str(message)

    out = []
    if fg:
        out.append(fg)
    if bg:
        out.append(bg)
    if style:
        out.append(style)
    out.extend((message, Style.RESET_ALL))
    return "".join(out)


class DiagnosticLevel:
    @dataclass
    class Level:
        label: str
        color: Fore

        def format(self, row: int, message: str) -> str:
            return f"line {row}: {self.color}{self.label}:{Fore.RESET} {message}"

        def colored(self, message: str):
            return decorated(message, fg=self.color)

    WARNING = Level("warning", Fore.YELLOW)
    ERROR   = Level("error", Fore.RED)


class Cancellation(Exception):
    ...


class ParseError(Exception):
    def __init__(self, message: str, context: str = "") -> None:
        super().__init__(message)
        self.context = context


T = TypeVar("T")


class PeekableStream:
    def __init__(self,
                 iterable: Iterable[T],
                 max_cache_size: Optional[int] = None,
                 default: Optional[T] = None):

        # !important: Do not reassign this. PeekableView will only see changes if we do not rebind
        self._cache: Deque[T] = deque([], maxlen=max_cache_size)

        self.__iterator: Iterator = iter(iterable)
        self._cursor: int = 0
        self.max_cache_size: Optional[int] = max_cache_size
        self.default: Optional[T] = default

    def __iter__(self):
        return self

    def __next__(self):
        # reset peek cursor
        self.revert()
        return self._cache.popleft() if self._cache else next(self.__iterator)

    def next(self, n=1):
        if n == 1:
            return next(self, self.default)
        return [next(self, self.default) for _ in range(n or 1)]

    def cache_next(self, *, advance_cursor=True, n=1):
        if n == 1:
            next_item = next(self.__iterator)
            self._cache.append(next_item)
        else:
            next_item = list(itertools.islice(self.__iterator, n))
            if not next_item:
                raise StopIteration
            self._cache.extend(next_item)

        if advance_cursor:
            self._cursor = len(self._cache)
        return next_item

    def peek(self, n: Optional[int] = None):
        if n is not None:
            return self.peek_n(n)

        if self._cursor < len(self._cache):
            item = self._cache[self._cursor]
            self._cursor += 1
            return item

        with contextlib.suppress(StopIteration):
            return self.cache_next()

        return self.default

    def peek_n(self, n: int) -> list[T]:
        needed = n - (len(self._cache) - self._cursor)
        cursor = self._cursor
        if needed > 0:
            with contextlib.suppress(StopIteration):
                self.cache_next(n=needed)

        items = list(itertools.islice(self._cache, 
                                      cursor, 
                                      cursor + n))

        needed = n - len(items)
        return items + [self.default for _ in range(needed)]

    def commit(self):
        # !important: this intentionally modifies the existing deque rather than rebinding to a new one
        remainder = list(itertools.islice(self._cache, self._cursor, None))
        self._cache.clear()
        self._cache.extend(remainder)
        self.revert()

    def revert(self):
        self._cursor = 0

    @property
    def rollback(parent):
        # pylint: disable=E0213

        class PeekableView(type(parent)):
            def __init__(self, iterable: PeekableStream,
                         max_cache_size: Optional[int] = None,
                         default: Optional[T] = None):
                super().__init__(parent, max_cache_size, default)
                self.__offset = getattr(parent, 'offset', 0)
                self._cursor = self.__offset
                # rebind to (mutable!) parent cache
                self._cache = parent._cache

            def __call__(self):
                return self

            def __iter__(self):
                return self

            def __enter__(self):
                return self

            def __exit__(self, type_, value, traceback):
                if type_ in (AssertionError, Cancellation):
                    # treat failed assertions as cancellations
                    return True

                # drop current cursor - use .commit to commit changes instead
                self.revert()
                self.commit(upstream=True)
                return False

            def __next__(self):
                try:
                    if self.__offset < len(self._cache):
                        item = self._cache[self.__offset]
                    else:
                        item = parent.cache_next(advance_cursor=False)
                except StopIteration:
                    pass
                else:
                    self.__offset += 1
                    self.revert()
                    return item

                return parent.default

            def cache_next(self, *, advance_cursor=True, n=1):
                next_item = parent.cache_next(advance_cursor=False, n=n)
                if advance_cursor:
                    self._cursor = len(self._cache)
                return next_item

            def commit(self, *, upstream=False):
                self.__offset = self._cursor
                self._cursor = 0

                if upstream:
                    parent._cursor = self.__offset
                    parent.commit()

            def revert(self):
                self._cursor = self.__offset

        return PeekableView(parent,
                            max_cache_size=parent.max_cache_size,
                            default=parent.default)


TokenQuery = tuple[int | list[int] | EllipsisType, 
                   str | re.Pattern | list[str | re.Pattern] | EllipsisType]
TokenNames: dict[int, str] = {value: key for key, value in token.__dict__.items() if isinstance(value, int)}


class Token(namedtuple("Token", ["type", "string"])):
    def __new__(cls, type: int, string: str, offset: Optional[int] = None):
        obj = super().__new__(cls, type, string)
        # add optional offset. Token must still behave like a 2-tuple for compatibility with tokenize.untokenize
        obj.offset = offset
        return obj

    def check_string(self, query: str | re.Pattern):
        if isinstance(query, re.Pattern):
            return query.match(self.string)
        elif isinstance(query, str):
            return self.string == query
        raise TypeError

    def to_code(self):
        prefix = '' if self.offset is None else self.offset * ' '
        return prefix + self.string

    def __bool__(self):
        return self.type != token.ENDMARKER

    def __str__(self):
        return f"({TokenNames.get(self.type, self.type)}, {self.string!r})"

    def __eq__(self, query: TokenQuery):
        query_type, query_string = query

        result = True  # wildcard (..., ...) matches everything

        if query_type is not ...:
            if isinstance(query_type, int):
                result &= query_type == self.type
            elif isinstance(query_type, Iterable):
                result &= any(type_ == self.type for type_ in query_type)
            else:
                raise TypeError
        if query_string is not ...:
            if isinstance(query_string, (str, re.Pattern)):
                result &= self.check_string(query_string)
            elif isinstance(query_string, Iterable):
                result &= any(self.check_string(needle) for needle in query_string)
            else:
                raise TypeError

        return result

    def __ne__(self, query: TokenQuery):
        return not self.__eq__(query)


def tokenize(code: str, with_endmarker: bool = False):
    last_line, last_column = 1, 0
    remove_indent = False
    indent = []

    for current in generate_tokens(StringIO(code).readline):
        if current.type == token.ENDMARKER and not with_endmarker:
            break
        cur_line, cur_column = current.end[0], current.start[1]

        if cur_line != last_line:
            last_line, last_column = cur_line, 0

        prepended_spaces = cur_column - last_column
        if remove_indent and indent:
            prepended_spaces = max(prepended_spaces - len(indent[-1]), 0)
            remove_indent = False

        last_column = cur_column + len(current.string)
        text = current.string
        if current.type == token.FSTRING_MIDDLE:
            # escape {}
            last_column += current.string.count('{') + current.string.count('}')
            text = current.string.replace('{', '{{').replace('}', '}}')

        elif current.type in (token.NL, token.NEWLINE):
            text = '\n'
            remove_indent = True
        elif current.type == token.INDENT:
            indent.append(current.string)
        elif current.type == token.DEDENT:
            with contextlib.suppress(IndexError):
                indent.pop()

        yield Token(current.type, text, offset=prepended_spaces)


def untokenize(tokens: Iterable[Token], last_type: Optional[int] = None):
    fragments = []
    indents = []
    last_type = last_type or 0
    for current in tokens:
        if current.type == token.ENCODING:
            continue
        elif current.type == token.ENDMARKER:
            break
        elif current.type == token.INDENT:
            last_indent = indents[-1] if indents else 0
            if len(current.string) <= last_indent:
                # treat the next indent as incremental if it's smaller than the last
                indents.append(last_indent + len(current.string))
            indents.append(len(current.string))
            continue
        elif current.type == token.DEDENT:
            with contextlib.suppress(IndexError):
                indents.pop()
            continue
        elif last_type in (token.NL, token.NEWLINE) and indents:
            fragments.append(indents[-1] * ' ')

        if getattr(current, 'offset', 0) == 0 and must_insert_space(last_type, current.type):
            # ensure spacing
            fragments.append(' ')

        fragments.append(current.to_code() if hasattr(current, 'to_code') else current.string)
        last_type = current.type
    return ''.join(fragments)


def must_insert_space(previous_type: int, current: Token):
    if previous_type in (token.STRING, token.FSTRING_START) and current.type in (token.FSTRING_END, token.STRING):
        # ensure a space between string literals
        return True
    elif previous_type == token.NAME and current.type in (token.NAME, token.NUMBER, token.STRING):
        # ensure a space between names (ie keyword + identifier)
        return True
    elif previous_type == current.type and current.type in (token.OP, token.NUMBER):
        # ie > = could be turned into one token >= accidentally. While this isn't valid Python,
        # preprocessors might want to use that.
        return True
    elif previous_type == token.NUMBER and current == (token.OP, '.'):
        return True
    return False


@cache
def get_tokens(data: str) -> list[Token]:
    return [Token(token.type, token.string) for token in list(generate_tokens(StringIO(data).readline))][:-1]


class TokenStream(PeekableStream):
    def __init__(self,
                 iterable: Iterable[Token],
                 max_cache_size: Optional[int] = None,
                 default: Optional[Token] = Token(token.ENDMARKER, '')):
        super().__init__(iterable, max_cache_size=max_cache_size, default=default)
        self.line_buffer = []
        self.lineno = 1

    def __next__(self):
        next_token: Token = super().__next__()
        if next_token.type in (token.NL, token.NEWLINE):
            # reset line buffer
            self.line_buffer = []
            self.lineno += 1
        else:
            self.line_buffer.append(next_token)
        return next_token

    def consume_if(self, needle: TokenQuery | list[TokenQuery]) -> Token | None:
        next_item = self.peek()
        if next_item == needle:
            self.commit()
            return next_item

        self._cursor -= 1  # unpeek
        return None

    @force_conversion(list)
    def consume_while(self, condition: TokenQuery) -> list[Token]:
        if not condition(self.peek()):
            return

        for item in self:
            yield item
            if item != condition:
                break

    @force_conversion(list)
    def consume_until(self, condition: TokenQuery) -> list[Token]:
        for item in self:
            yield item
            if item == condition:
                break

    def consume_line(self) -> list[Token]:
        return self.consume_until(([token.NL, token.NEWLINE, token.ENDMARKER], ...))

    @force_conversion(list)
    def consume_balanced(self, increase: TokenQuery, decrease: TokenQuery, level: int = 0) -> list[Token]:
        for item in self:
            yield item

            if item == increase:
                level += 1
            elif item == decrease:
                level -= 1
                if level <= 0:
                    break
        else:
            if level == 0:
                return
            raise ParseError(f"Unexpected eof - expected {decrease}", self.error_context())

    def consume_block(self) -> list[Token]:
        return self.consume_balanced((token.INDENT, ...), (token.DEDENT, ...))

    @force_conversion(list)
    def peek_while(self, condition: TokenQuery) -> list[Token]:
        while (next_item := self.peek()):
            yield next_item
            if next_item != condition:
                break

    @force_conversion(list)
    def peek_until(self, condition: TokenQuery) -> list[Token]:
        while (next_item := self.peek()):
            yield next_item
            if next_item == condition:
                break

    def peek_line(self):
        return self.peek_until(([token.NL, token.NEWLINE, token.ENDMARKER], ...))

    @force_conversion(list)
    def peek_balanced(self, increase: TokenQuery, decrease: TokenQuery, level: int = 0) -> list[Token]:
        peeked = []
        while (item := self.peek()):
            peeked.append(item)

            if item == increase:
                level += 1

            elif item == decrease:
                level -= 1

                if level == 0:
                    break
        else:
            if level != 0:
                return []
            # raise ParseError(f"Unexpected eof - expected {decrease}", self.error_context())
        return peeked

    def peek_block(self):
        return self.peek_balanced((token.INDENT, ...), (token.DEDENT, ...))

    def error_context(self):
        if not self.line_buffer and not self._cursor:
            # token stream hasn't been used yet, cancel
            return
        if not self._cursor:
            tokens_before = self.line_buffer[:-1]
            current_token = self.line_buffer[-1]
        else:
            cursor = min(self._cursor - 1, len(self._cache) - 1)
            cached_prefix = list(itertools.islice(self._cache, 0, cursor)) if cursor > 0 else []
            tokens_before = [*self.line_buffer, *cached_prefix]
            current_token = self._cache[cursor]

        last_type = None
        line_prefix = ""
        if tokens_before:
            # could pass untokenize last_type=token.NL to attempt indentation
            # however we do not currently track in this context
            last_newline = 0
            with contextlib.suppress(ValueError):
                last_newline = list(reversed(tokens_before)).index(([token.NL, token.NEWLINE], ...))

            tokens_before = tokens_before[-last_newline:]
            line_prefix = untokenize(tokens_before)
            last_type = tokens_before[-1].type

        if current_token == ([token.NL, token.NEWLINE], ...):
            current = ""
        else:
            current = untokenize([current_token], last_type=last_type)

        old_cursor = self._cursor
        tokens_after = self.peek_line()
        line_suffix = untokenize(tokens_after, last_type=current_token.type)
        self._cursor = old_cursor

        token_str = str(current_token)
        prefix = ' ' * (len(line_prefix) + 1)

        style = {'fg': Fore.RED, 'style': Style.BRIGHT}
        squiggly_line = decorated(f"{prefix}^" + (len(token_str) - 1) * '~', **style)
        current = decorated(current, **style)
        token_str = decorated(token_str, **style)

        indent = 4 * ' '
        return f"{indent}{line_prefix}{current}{line_suffix}\n{indent}{squiggly_line}\n{indent}{prefix} {token_str}"


class Code:
    __current_state: str | list[Token] | _ast.AST

    def __init__(self, state: str | list[Token] | _ast.AST | Self):
        self.__current_state = state.__current_state if isinstance(state, Code) else state
        if isinstance(self.__current_state, Iterable) and not isinstance(self.__current_state, str):
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
        if isinstance(self.__current_state, Iterable) and not isinstance(self.__current_state, str):
            return self.__current_state
        return get_tokens(self.string)
