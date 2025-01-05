import codecs
import importlib
import traceback
from typing import Callable, Optional
from collections.abc import Buffer


class CodecError(Exception):
    ...


def make_decoder(preprocessor: Callable):
    class Decoder(codecs.IncrementalDecoder):
        def __init__(self, errors='strict'):
            super().__init__(errors)
            self.buffer = b""

        @staticmethod
        def do_decode(data: Buffer, errors='strict') -> tuple[str, int]:
            decoded, consumed = codecs.utf_8_decode(data, errors, True)
            try:
                processed = preprocessor(decoded)
            except Exception:
                traceback.print_exc()
                raise

            return processed, consumed

        def decode(self, input, final=False) -> str:
            self.buffer += input

            if self.buffer and final:
                buffer = self.buffer
                self.reset()
                return self.do_decode(buffer, self.errors)[0]

            return ""

        def reset(self):
            super().reset()
            self.buffer = b""

        def getstate(self):
            return (self.buffer, 0)

        def setstate(self, state):
            self.buffer = state[0]

    return Decoder


def get_preprocessor(module_name: str, package_name: Optional[str] = None) -> Callable:
    try:
        # force relative import if package_name is set
        module_path = f".{module_name}" if package_name else module_name

        module = importlib.import_module(module_path, package_name)
    except ModuleNotFoundError as exc:
        if exc.name == package_name:
            raise CodecError(f"Invalid magic_codec: `{module_name}` not found") from exc
        raise

    preprocessor = getattr(module, "preprocess", None)
    if preprocessor is None:
        raise CodecError(f"Invalid magic_codec: preprocess() is not present in module `{module_name}`")

    return preprocessor


def find_codec(encoding: str) -> Optional[codecs.CodecInfo]:
    prefix = "magic"
    if len(encoding) < len(prefix) + 1 or not encoding.startswith(prefix):
        # the requested codec couldn't possibly be one of ours, do nothing
        return None

    try:
        if (separator := encoding[len(prefix)]) == '.':
            # builtins (ie. magic.cpp)
            name = encoding[len(prefix) + 1:]
            preprocessor = get_preprocessor(name, "magic_codec.builtin")
        elif separator == '_':
            # extension packages (ie. magic_example)
            preprocessor = get_preprocessor(encoding)
        else:
            print(f"Invalid magic_codec: Invalid separator {separator}")
            return None

        decoder = make_decoder(preprocessor)
        return codecs.CodecInfo(
            name=encoding,
            encode=codecs.utf_8_encode,
            decode=decoder.do_decode,
            incrementaldecoder=decoder
        )
    except CodecError as exc:
        print(exc)
    except Exception:
        traceback.print_exc()

    return None
