import builtins
import ctypes
import sys
import termios
import threading
import tty
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from queue import Queue

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
    builtins._loop = loop
    builtins._give = give


def do(fn, args, kwargs):
    out = FileGiver("#stdout")
    err = FileGiver("#stderr")

    with redirect_stdout(out), redirect_stderr(err):
        try:
            givex(result=fn(*args, **kwargs), status="done")
        except AbortRun:
            givex(status="aborted")
            raise
        except Exception as error:
            givex(error, status="error")


class AbortRun(Exception):
    pass


def kill_thread(thread, exctype=AbortRun):
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread.ident), ctypes.py_object(exctype)
    )


@contextmanager
def cbreak():
    old_attrs = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin)
    try:
        yield
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attrs)


def read_chars():
    while True:
        yield {"char": sys.stdin.read(1)}


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
        self.lv = Live(auto_refresh=False)

    def register_updates(self, gv):
        def update(_=None):
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
                    show_locals=True,
                )
                panels.append(tb)

            has_result = "result" in results
            if has_result:
                panels.append(Panel(Pretty(results["result"]), title="result"))

            status = results["status"]
            footer = [
                f"#{self.num} ({status})",
                "[bold](r)[/bold]erun",
                "[bold](Enter)[/bold] return",
                "[bold](q)[/bold]uit",
                (not has_result) and "[red][bold](a)[/bold]bort[/red]",
            ]

            panels.append(markup(" | ".join(x for x in footer if x)))

            with redirect_stdout(real_stdout):
                self.lv.update(Group(*panels), refresh=True)

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
        (
            gv.debounce(0.05) | gv.delay(0.25).throttle(0.25) | gv.last()
        ) >> update

    def run(self):
        self.num += 1
        outcome = [None, None]  # [result, error]
        with given() as gv:
            gv["?#result"] >> itemsetter(outcome, 0)
            gv["?#error"] >> itemsetter(outcome, 1)
            self.register_updates(gv)
            do(self.fn, self.args, self.kwargs)
        return outcome

    def loop(self):
        def setcommand(cmd):
            while not q.empty():
                q.get()
            q.put(cmd)

        def run():
            nonlocal result, err
            result, err = self.run()

        def command(name, aborts=False):
            def perform(_=None):
                if aborts:
                    # Asynchronously sends the AbortRun exception to the
                    # thread in which the function runs.
                    kill_thread(loop_thread)
                setcommand(name)

            return perform

        result = None
        err = None
        q = Queue()
        setcommand("go")
        loop_thread = threading.current_thread()

        with self.lv:
            with cbreak(), watching_changes() as chgs:
                scheduler = rx.scheduler.EventLoopScheduler()
                keypresses = ObservableProxy(
                    rx.from_iterable(read_chars(), scheduler=scheduler)
                ).share()

                keypresses.where(char="a") >> command("abort", aborts=True)
                keypresses.where(char="q") >> command("quit", aborts=True)
                keypresses.where(char="\n") >> command("stop")
                keypresses.where(char="r") >> command("go", aborts=True)
                chgs.debounce(0.05) >> command("go", aborts=True)

                while True:
                    try:
                        cmd = q.get()
                        if cmd == "go":
                            run()
                        elif cmd == "stop":
                            break
                        elif cmd == "abort":
                            pass
                        elif cmd == "quit":
                            sys.exit(1)

                    except AbortRun:
                        continue

        if err is not None:
            raise err
        else:
            return result


class Develoop:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args, **kwargs):
        return DeveloopRunner(self.fn, args, kwargs).loop()


loop = Develoop
