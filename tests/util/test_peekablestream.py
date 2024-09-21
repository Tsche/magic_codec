import pytest
from magic_codec.util import Cancellation, PeekableStream

# Assuming Token class code is here

@pytest.fixture
def stream():
    return PeekableStream(range(10))


def test_iterate(stream):
    for expected, actual in zip(range(10), stream):
        assert expected == actual

    assert stream.peek() is None
    assert stream.next() is None

    assert stream.peek(2) == [None, None]
    assert stream.next(2) == [None, None]


def test_manual_iteration(stream):
    assert stream.next() == 0
    assert stream.peek() == 1
    assert stream.next() == 1

    assert stream.next(2) == [2, 3]
    assert stream.peek(2) == [4, 5]
    assert stream.peek() == 6
    stream.commit()
    assert stream.next(4) == [7, 8, 9, None]

    assert stream.peek() is None
    assert stream.next() is None
    assert stream.peek(2) == [None, None]
    assert stream.next(2) == [None, None]


def test_commit_while_iterating(stream):
    def process():
        for item in stream:
            stream.peek()
            stream.commit()
            yield item

    assert list(process()) == [0, 2, 4, 6, 8]


def test_rollback(stream):
    assert stream.next() == 0

    # do not use context manager here - it would eat up assertions
    lookahead = stream.rollback

    assert lookahead.peek() == 1
    assert lookahead.next() == 1
    assert lookahead.peek() == 2

    assert stream.next() == 1

    # changes to the parent do not invalidate lookahead cursor
    # but lookahead.next() will skip items and can no longer be used
    assert lookahead.peek() == 3

    # parent still sees the otherwise skipped items though
    assert stream.peek() == 2

    # reset the lookahead view
    lookahead = stream.rollback
    assert lookahead.next() == 2
    lookahead.commit(upstream=True)

    # nested lookahead view
    lookahead_2 = lookahead.rollback

    assert lookahead_2.peek() == 3
    assert lookahead_2.peek() == 4
    lookahead_2.commit()
    assert lookahead_2.next() == 5
    lookahead_2.commit(upstream=True)

    assert lookahead.next() == 6


def test_context_manager(stream):
    assert stream.next() == 0
    with stream.rollback as lookahead:
        assert lookahead.next() == 1
    assert stream.next() == 2

    with stream.rollback as lookahead:
        assert lookahead.next() == 3
        raise Cancellation
    assert stream.next() == 3

    with stream.rollback as lookahead:
        assert lookahead.next() == 4
        assert False
    assert stream.next() == 4
