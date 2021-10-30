import builtins
import ctypes
import select
import sys
import termios
import threading
import tty
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from functools import partial
from queue import Queue
from types import SimpleNamespace

import rx
from giving import ObservableProxy, SourceProxy, give, given
from rich.console import Group
from rich.live import Live
from rich.markup import render as markup
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table
from rich.traceback import Traceback

from .register import registry

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


def inject():
    builtins.__ = __


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


@contextmanager
def cbreak():
    old_attrs = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin)
    try:
        yield
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attrs)


def read_chars():
    try:
        while True:
            if select.select([sys.stdin], [], [], 0.02):
                yield {"char": sys.stdin.read(1)}
    except Abort:
        pass


class RichDeveloopRunner(DeveloopRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lv = Live(auto_refresh=False)

    def _update(self, results):
        panels = []
        if stdout := results.get("stdout", None):
            panels.append(Panel(stdout.rstrip(), title="stdout"))
        if stderr := results.get("stderr", None):
            panels.append(Panel(stderr.rstrip(), title="stderr"))
        if gvn := results.get("given", None):
            table = Table.grid(padding=(0, 3, 0, 0))
            table.add_column("key", style="bold green")
            table.add_column("value")
            for k, v in gvn.items():
                table.add_row(k, Pretty(v))
            panels.append(Panel(table, title="given"))

        if error := results.get("error", None):
            tb = Traceback(
                trace=Traceback.extract(
                    type(error), error, error.__traceback__
                ),
                suppress=["jurigged"],
                extra_lines=0,
            )
            panels.append(tb)

        has_result = "result" in results
        if has_result:
            panels.append(Panel(Pretty(results["result"]), title="result"))

        status = results["status"]
        footer = [
            f"#{self.num} ({status})",
            "[bold](c)[/bold]ontinue",
            "[bold](r)[/bold]erun",
            (not has_result and not error) and "[bold](a)[/bold]bort",
            "[bold](q)[/bold]uit",
        ]

        panels.append(markup(" | ".join(x for x in footer if x)))

        with redirect_stdout(real_stdout):
            self.lv.update(Group(*panels), refresh=True)

    @contextmanager
    def wrap_loop(self):
        with self.lv, cbreak():
            try:
                scheduler = rx.scheduler.EventLoopScheduler()
                keypresses = ObservableProxy(
                    rx.from_iterable(read_chars(), scheduler=scheduler)
                ).share()

                keypresses.where(char="c") >> self.command("cont")
                keypresses.where(char="r") >> self.command("go", aborts=True)
                keypresses.where(char="a") >> self.command("abort", aborts=True)
                keypresses.where(char="q") >> self.command("quit", aborts=True)

                yield

            finally:
                kill_thread(scheduler._thread)
                scheduler.dispose()

    def register_updates(self, gv):
        gvn = {}
        results = {
            "stdout": "",
            "stderr": "",
            "given": gvn,
            "status": "running",
        }

        # Append stdout/stderr incrementally
        gv["?#stdout"] >> itemappender(results, "stdout")
        gv["?#stderr"] >> itemappender(results, "stderr")

        # Set result and error when we get it
        gv["?#result"] >> itemsetter(results, "result")
        gv["?#error"] >> itemsetter(results, "error")
        gv["?#status"] >> itemsetter(results, "status")

        # Fill given table
        @gv.subscribe
        def fill_given(d):
            gvn.update(
                {
                    k: v
                    for k, v in d.items()
                    if not k.startswith("#") and not k.startswith("$")
                }
            )

        # TODO: this may be a bit wasteful
        # Debounce is used to ignore events if they are followed by another
        # event less than 0.05s later. Delay + throttle ensures we get at
        # least one event every 0.25s. We of course update as soon as the
        # last event is in.
        (gv.debounce(0.05) | gv.delay(0.25).throttle(0.25) | gv.last()) >> (
            lambda _: self._update(results)
        )


class Develoop:
    def __init__(self, fn, on_error=False, runner_class=RichDeveloopRunner):
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


loop = Develoop
loop_on_error = partial(Develoop, on_error=True)

__ = SimpleNamespace(
    loop=loop,
    loop_on_error=loop_on_error,
    xloop=loop_on_error,
    give=give,
    given=given,
)
