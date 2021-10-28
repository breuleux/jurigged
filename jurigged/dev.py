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


def inject():
    builtins._loop = loop
    builtins._give = give


def do(fn, args, kwargs):
    out = io.StringIO()
    err = io.StringIO()

    results = {}

    with given() as gv:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                results["result"] = fn(*args, **kwargs)
            except KeyboardInterrupt as exc:
                raise
            except Exception as exc:
                results["error"] = exc
            finally:
                results["stdout"] = out.getvalue()
                results["stderr"] = err.getvalue()

    return results


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
        self.lv = Live()

    def update(self, results):
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

        self.lv.update(Group(*panels))

    def run(self):
        results = do(self.fn, self.args, self.kwargs)
        self.update(results)
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
                    rx.from_iterable(
                        read_chars(),
                        scheduler=scheduler
                    )
                ).share()

                with given() as gv:
                    keypresses.where(char="\n") >> stop
                    keypresses.where(char="r") >> go
                    chgs >> go

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
