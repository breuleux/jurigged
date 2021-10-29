import builtins
import io
import sys
import termios
import tty
from contextlib import contextmanager, redirect_stderr, redirect_stdout

import rx
from giving import ObservableProxy, SourceProxy, give, given
from rich.console import Group
from rich.live import Live
from rich.markup import render as markup
from rich.panel import Panel
from rich.pretty import Pretty
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
            givex(result=fn(*args, **kwargs))
        except KeyboardInterrupt as exc:
            raise
        except Exception as error:
            givex(error)


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
        self.lv = Live(auto_refresh=False)

    def register_updates(self, gv):
        def update(_=None):
            panels = []
            if stdout := results.get("stdout", None):
                panels.append(Panel(stdout.rstrip(), title="stdout"))
            if stderr := results.get("stderr", None):
                panels.append(Panel(stderr.rstrip(), title="stderr"))
            if error := results.get("error", None):
                tb = Traceback(
                    trace=Traceback.extract(
                        type(error), error, error.__traceback__
                    ),
                    suppress=["jurigged"],
                    show_locals=True,
                )
                panels.append(tb)
            if "result" in results:
                panels.append(Panel(Pretty(results["result"]), title="result"))
            panels.append(
                markup("[bold](r)[/bold]erun | [bold](Enter)[/bold] return")
            )

            with redirect_stdout(real_stdout):
                self.lv.update(Group(*panels), refresh=True)

        results = {
            "stdout": "",
            "stderr": "",
        }

        # Append stdout/stderr incrementally
        gv["?#stdout"] >> itemappender(results, "stdout")
        gv["?#stderr"] >> itemappender(results, "stderr")

        # Set result and error when we get it
        gv["?#result"] >> itemsetter(results, "result")
        gv["?#error"] >> itemsetter(results, "error")

        # TODO: this may be a bit wasteful
        # Debounce is used to ignore events if they are followed by another
        # event less than 0.05s later. Delay + throttle ensures we get at
        # least one event every 0.25s. We of course update as soon as the
        # last event is in.
        (
            gv.debounce(0.05) | gv.delay(0.25).throttle(0.25) | gv.last()
        ) >> update
        return results

    def run(self):
        with given() as gv:
            results = self.register_updates(gv)
            do(self.fn, self.args, self.kwargs)
        return results.get("result", None), results.get("error", None)

    def loop(self):
        result = None
        err = None

        def go(_=None):
            nonlocal result, err
            result, err = self.run()

        def stop(_=None):
            scheduler.dispose()

        with self.lv:
            with cbreak(), watching_changes() as chgs:
                scheduler = rx.scheduler.EventLoopScheduler()
                keypresses = ObservableProxy(
                    rx.from_iterable(read_chars(), scheduler=scheduler)
                ).share()

                keypresses.where(char="\n") >> stop
                keypresses.where(char="r") >> go
                chgs.debounce(0.05) >> go

                go()
                scheduler.run()

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
