import select
import sys
import termios
import tty
from contextlib import contextmanager, redirect_stdout

import rx
from giving import ObservableProxy
from rich.console import Group
from rich.live import Live
from rich.markup import render as markup
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table
from rich.traceback import Traceback

from .develoop import (
    Abort,
    DeveloopRunner,
    itemappender,
    itemsetter,
    kill_thread,
)

real_stdout = sys.stdout


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
