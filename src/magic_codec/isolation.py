from multiprocessing.connection import Connection
import os
import importlib
import marshal
from multiprocessing import Pipe, get_context


def try_import(names: list[str], default=None):
    for name in names:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            pass
    if not default:
        raise ModuleNotFoundError(f"Could not find any of the packages {names}")
    return default


class Subinterpreter:
    uses_multiprocessing = True
    class InterpreterSession:
        def __init__(self):
            exec_fd_r, self.exec_fd = Pipe()
            self.eval_fd, eval_fd_w = Pipe()
            ctx = get_context("spawn")
            self.process = ctx.Process(target=self.init_func, args=(exec_fd_r, eval_fd_w))
            self.process.start()
            exec_fd_r.close()

        @staticmethod
        def init_func(_exec_fd, _eval_fd):
            default_globals = globals().copy()
            while obj := _exec_fd.recv():
                must_eval, code, globals_ = obj
                if must_eval:
                    _eval_fd.send(eval(code, default_globals, globals_ or default_globals))
                else:
                    exec(code, default_globals, globals_ or default_globals)

        def exec(self, code, globals_: dict):
            self.exec_fd.send((False, str(code), globals_))

        def eval(self, code, globals_: dict):
            self.exec_fd.send((True, str(code), globals_))
            return self.eval_fd.recv()

        def kill(self):
            self.exec_fd.send(None)
            self.process.join()
            self.process.close()

    subinterpreters: dict[int, InterpreterSession] = {}
    interpreter_id: int = 1

    @classmethod
    def create(cls):
        ident = cls.interpreter_id
        cls.subinterpreters[cls.interpreter_id] = cls.InterpreterSession()
        cls.interpreter_id += 1
        return ident

    @classmethod
    def destroy(cls, interp: int):
        cls.subinterpreters[interp].kill()
        del cls.subinterpreters[interp]

    @classmethod
    def run_string(cls, interp: int, code: str, globals_: dict):
        cls.subinterpreters[interp].exec(code, globals_)

    @classmethod
    def eval_string(cls, interp: int, code: str, globals_: dict):
        return cls.subinterpreters[interp].eval(code, globals_)


interpreters = try_import(
    ["interpreters", '_xxsubinterpreters', '_interpreters'],
    Subinterpreter)

assert "create" in interpreters.__dict__ and callable(interpreters.create)
assert "destroy" in interpreters.__dict__ and callable(interpreters.destroy)
assert "run_string" in interpreters.__dict__ and callable(interpreters.run_string)


class Isolation:
    def __init__(self, interp = None):
        self.interp = interp

    def __enter__(self):
        self.interp = interpreters.create()
        return self
    
    def __exit__(self, *_):
        interpreters.destroy(self.interp)

    def exec(self, code, globals_=None):
        globals_ = {} if not globals_ else globals_.copy()
        interpreters.run_string(self.interp, code, globals_)

    def eval(self, expr, globals_=None):
        globals_ = {} if not globals_ else globals_.copy()
        if hasattr(interpreters, "eval_string"):
            return interpreters.eval_string(self.interp, expr, globals_)
        else:
            read_end, write_end = os.pipe()
            globals_['_comm'] = write_end
            code = f"""
import os
import marshal
with os.fdopen(_comm, 'wb') as out:
    out.write(marshal.dumps({expr}))
"""
        interpreters.run_string(self.interp, code, globals_)
        assert isinstance(read_end, int)
        with os.fdopen(read_end, 'rb') as pipe:
            return marshal.loads(pipe.read())
