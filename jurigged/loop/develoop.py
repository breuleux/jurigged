import ctypes
import linecache
import sys
import threading
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from queue import Queue
from types import FunctionType
from typing import Union

from executing import Source
from giving import SourceProxy, give, given
from ovld import ovld

from ..register import registry

NoneType = type(None)


@ovld
def pstr(x: Union[int, float, bool, NoneType]):
    return str(x)


@ovld
def pstr(x: str):
    if len(x) > 15:
        return repr(x[:12] + "...")
    else:
        return repr(x)


@ovld
def pstr(x: FunctionType):
    name = x.__qualname__
    return f"<function {name}>"


@ovld
def pstr(x: object):
    name = type(x).__qualname__
    return f"<{name}>"


@registry.activity.append
def _(evt):
    # Patch to ensure the executing module's cache is invalidated whenever
    # a source file is changed.
    cache = Source._class_local("__source_cache", {})
    filename = evt.codefile.filename
    if filename in cache:
        del cache[filename]
    linecache.checkcache(filename)


@give.variant
def givex(data):
    return {f"#{k}": v for k, v in data.items()}


def itemsetter(coll, key):
    def setter(value):
        coll[key] = value

    return setter


def itemappender(coll, key):
    def appender(value):
        coll[key] += value

    return appender


class FileGiver:
    def __init__(self, name):
        self.name = name

    def write(self, x):
        give(**{self.name: x})

    def flush(self):
        pass


class Abort(Exception):
    pass


def kill_thread(thread, exctype=Abort):
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread.ident), ctypes.py_object(exctype)
    )


@contextmanager
def watching_changes():
    src = SourceProxy()
    registry.activity.append(src._push)
    try:
        yield src
    finally:
        registry.activity.remove(src._push)


class DeveloopRunner:
    def __init__(self, fn, args, kwargs):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.num = 0
        self._q = Queue()

    def setcommand(self, cmd):
        while not self._q.empty():
            self._q.get()
        self._q.put(cmd)

    def command(self, name, aborts=False):
        def perform(_=None):
            if aborts:
                # Asynchronously sends the Abort exception to the
                # thread in which the function runs.
                kill_thread(self._loop_thread)
            self.setcommand(name)

        return perform

    def signature(self):
        name = getattr(self.fn, "__qualname__", str(self.fn))
        parts = [pstr(arg) for arg in self.args]
        parts += [f"{k}={pstr(v)}" for k, v in self.kwargs.items()]
        args = ", ".join(parts)
        return f"{name}({args})"

    @contextmanager
    def wrap_loop(self):
        yield

    @contextmanager
    def wrap_run(self):
        yield

    def register_updates(self, gv):
        raise NotImplementedError()

    def run(self):
        self.num += 1
        outcome = [None, None]  # [result, error]
        with given() as gv, self.wrap_run():
            t0 = time.time()
            gv["?#result"] >> itemsetter(outcome, 0)
            gv["?#error"] >> itemsetter(outcome, 1)
            self.register_updates(gv)
            try:
                givex(result=self.fn(*self.args, **self.kwargs), status="done")
            except Abort:
                givex(status="aborted")
                raise
            except Exception as error:
                givex(error, status="error")
            givex(walltime=time.time() - t0)
        return outcome

    def loop(self, from_error=None):
        self._loop_thread = threading.current_thread()
        result = None
        err = None

        if from_error:
            self.setcommand("from_error")
        else:
            self.setcommand("go")

        with self.wrap_loop(), watching_changes() as chgs:
            chgs.debounce(0.05) >> self.command("go", aborts=True)

            while True:
                try:
                    cmd = self._q.get()
                    if cmd == "go":
                        result, err = self.run()
                    elif cmd == "cont":
                        break
                    elif cmd == "abort":
                        pass
                    elif cmd == "quit":
                        sys.exit(1)
                    elif cmd == "from_error":
                        with given() as gv:
                            self.register_updates(gv)
                            givex(error=from_error, status="error")
                        result, err = None, from_error

                except Abort:
                    continue

        if err is not None:
            raise err
        else:
            return result


class RedirectDeveloopRunner(DeveloopRunner):
    @contextmanager
    def wrap_run(self):
        out = FileGiver("#stdout")
        err = FileGiver("#stderr")

        with redirect_stdout(out), redirect_stderr(err):
            yield


class Develoop:
    def __init__(self, fn, on_error, runner_class):
        self.fn = fn
        self.on_error = on_error
        self.runner_class = runner_class

    def __get__(self, obj, cls):
        return type(self)(
            self.fn.__get__(obj, cls),
            on_error=self.on_error,
            runner_class=self.runner_class,
        )

    def __call__(self, *args, **kwargs):
        exc = None
        if self.on_error:
            try:
                return self.fn(*args, **kwargs)
            except Exception as _exc:
                exc = _exc

        return self.runner_class(self.fn, args, kwargs).loop(from_error=exc)
