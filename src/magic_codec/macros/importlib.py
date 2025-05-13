from importlib.machinery import PathFinder, SourceFileLoader
import marshal
from pathlib import Path
from tokenize import detect_encoding

from magic_codec.macros.evaluator import transform
from magic_codec.macros.macro_ast import MACRO_PREFIX, Code, demangle


class MacroFileLoader(SourceFileLoader):
    def __init__(self, fullname: str, path: str, macro_only: bool = False) -> None:
        super().__init__(fullname, path)
        self.macro_only = macro_only

    def process_macros(self):
        source, meta = transform(Path(self.path).read_text(), Path(self.path))
        return source, meta

    def make_macro_path(self, path: Path | str):
        path_ = Path(path)
        return path_.with_stem(f"{MACRO_PREFIX}{path_.stem}")

    def set_data(self, path: str, data, *, _mode: int = 438) -> None:
        print(f"recompiling {self.path}")
        super().set_data(path, data, _mode=_mode)

        macro_path = self.make_macro_path(path)
        macro_source_path = self.make_macro_path(self.path)
        _, macros = self.process_macros()

        # copy header from the primary cache file
        macro_data = bytearray(data[:16])
        macro_data.extend(marshal.dumps(compile(Code(macros).string, macro_source_path, mode="exec")))
        super().set_data(str(macro_path), macro_data, _mode=_mode)

    def get_code(self, fullname):
        if self.macro_only:
            # try to get code for the base module
            parts = fullname.split('.')
            parts[-1] = demangle(parts[-1])
            base_name = '.'.join(parts)

            # force loading the base module code object
            # this refreshes the caches and triggers recompilation if necessary
            base_loader = MacroFileLoader(base_name, self.path, False)
            code = base_loader.get_code(base_name)

            #! note that this will fail to regenerate the macro cache
            #! if the macro cache is missing but the primary module cache
            #! still exists and is up to date

        return super().get_code(fullname)

    def get_data(self, path: str) -> bytes:
        path_ = Path(path)
        if not path_.exists():
            return b''

        if path_.suffix != ".py":
            # module has already been compiled
            return super().get_data(self.make_macro_path(path) if self.macro_only else str(path))

        with open(path, 'rb') as source:
            assert self.path == str(path), f"Path mismatch {self.path} != {path}"
            # read in raw data here to force module recompilation whenever the file changes
            # regardless of if the change was made to the macro or primary module part
            return source.read()


class MacroFinder(PathFinder):
    @staticmethod
    def uses_macro_codec(path):
        with open(path, 'rb') as source:
            encoding, *_ = detect_encoding(source.readline)
            return encoding == "magic.macro"

    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        macro_only = False
        processed_name = fullname
        parts = fullname.split('.')
        if parts[-1].startswith(MACRO_PREFIX):
            # the module was imported via name! bang-name
            # => we're only interested in this module's macros
            parts[-1] = parts[-1].removeprefix(MACRO_PREFIX)
            processed_name = '.'.join(parts)
            macro_only = True

        if not (spec := super().find_spec(processed_name, path, target)):
            return

        if not (spec.origin and isinstance(spec.loader, SourceFileLoader)):
            # we cannot process macros unless we have an origin
            return

        if cls.uses_macro_codec(spec.origin):
            spec.name = fullname
            spec.loader = MacroFileLoader(fullname, spec.origin, macro_only)
            return spec


def install_import_hook():
    # This needs to be called within the macro preprocessor context
    # to allow importing macros from other modules, even if they
    # have already been compiled
    import sys
    sys.meta_path.insert(0, MacroFinder())