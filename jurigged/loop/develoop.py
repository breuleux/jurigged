import ctypes
import sys
import threading
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from queue import Queue

from giving import SourceProxy, give, given

from ..register import registry

real_stdout = sys.stdout


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


def do(fn, args, kwargs):
    out = FileGiver("#stdout")
    err = FileGiver("#stderr")

    with redirect_stdout(out), redirect_stderr(err):
        try:
            givex(result=fn(*args, **kwargs), status="done")
        except Abort:
            givex(status="aborted")
            raise
        except Exception as error:
            givex(error, status="error")


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

    @contextmanager
    def wrap_loop(self):
        yield

    def register_updates(self, gv):
        raise NotImplementedError()

    def run(self):
        self.num += 1
        outcome = [None, None]  # [result, error]
        with given() as gv:
            gv["?#result"] >> itemsetter(outcome, 0)
            gv["?#error"] >> itemsetter(outcome, 1)
            self.register_updates(gv)
            do(self.fn, self.args, self.kwargs)
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


class Develoop:
    def __init__(self, fn, on_error, runner_class):
        self.fn = fn
        self.on_error = on_error
        self.runner_class = runner_class

    def __get__(self, obj, cls):
        return type(self)(self.fn.__get__(obj, cls), on_error=self.on_error)

    def __call__(self, *args, **kwargs):
        exc = None
        if self.on_error:
            try:
                return self.fn(*args, **kwargs)
            except Exception as _exc:
                exc = _exc

        return self.runner_class(self.fn, args, kwargs).loop(from_error=exc)
