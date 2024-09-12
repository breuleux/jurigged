import re
import select
import sys
import termios
import traceback
import tty
from contextlib import contextmanager
from functools import partial

from .develoop import Abort, DeveloopRunner

ANSI_ESCAPE = re.compile(r"\x1b\[[;\d]*[A-Za-z]")
ANSI_ESCAPE_INNER = re.compile(r"[\x1b\[;\d]")
ANSI_ESCAPE_END = re.compile(r"[A-Za-z~]")


@contextmanager
def cbreak():
    old_attrs = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin)
    try:
        yield
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attrs)


def read_chars():
    esc = None
    try:
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.02)
            if ready:
                # Sometimes, e.g. when pressing an up arrow, multiple
                # characters are buffered, and read1() is the only way
                # I found to read precisely what was buffered. select
                # seems unreliable in these cases, probably because the
                # buffer fools it into thinking there is nothing else
                # to read. So read(1) would leave some characters dangling
                # in the buffer until the next keypress.
                for ch in sys.stdin.buffer.read1():
                    ch = chr(ch)
                    if esc is not None:
                        if ANSI_ESCAPE_INNER.match(ch):
                            esc += ch
                        elif ANSI_ESCAPE_END.match(ch):
                            yield {"char": esc + ch, "escape": True}
                            esc = None
                        else:
                            yield {"char": esc, "escape": True}
                            esc = None
                            yield {"char": ch}
                    elif ch == "\x1b":
                        esc = ""
                    else:
                        yield {"char": ch}
    except Abort:
        pass


class BasicDeveloopRunner(DeveloopRunner):
    def __init__(self, fn, args, kwargs):
        super().__init__(fn, args, kwargs)
        self._status = "running"
        self._walltime = 0

    def _pad(self, text, total):
        text = f"#{self.num}: {text}"
        rest = total - len(text) - 6
        return f"---- {text} " + "-" * rest

    def _finish(self, status, result):
        print(self._pad(status, 50))
        if status == "ERROR":
            traceback.print_exception(
                type(result), result, result.__traceback__
            )
        else:
            print(f"{result}")

        footer = [
            "(c)ontinue",
            "(r)erun",
            "(q)uit",
        ]
        print(self._pad(" | ".join(footer), 50))

        with cbreak():
            for c in read_chars():
                if c["char"] == "c":
                    self.command("cont")()
                    break
                elif c["char"] == "r":
                    self.command("go")()
                    break
                elif c["char"] == "q":
                    self.command("quit")()
                    break

    def register_updates(self, gv):
        print(self._pad(self.signature(), 50))

        gv["?#result"] >> partial(self._finish, "RESULT")
        gv["?#error"] >> partial(self._finish, "ERROR")

        gv.filter(
            lambda d: not any(
                k.startswith("#") and not k.startswith("$") for k in d.keys()
            )
        ).display()

        def _on(key):
            # black and vscode's syntax highlighter both choke on parsing the following
            # as a decorator, that's why I made a function
            return gv.getitem(key, strict=False).subscribe

        @_on("#status")
        def _(status):
            self._status = status

        @_on("#walltime")
        def _(walltime):
            self._walltime = walltime


def readable_duration(t):
    if t < 0.001:
        return "<1ms"
    elif t < 1:
        t = int(t * 1000)
        return f"{t}ms"
    elif t < 10:
        return f"{t:.3f}s"
    elif t < 60:
        return f"{t:.1f}s"
    else:
        s = t % 60
        m = (t // 60) % 60
        if t < 3600:
            return f"{m:.0f}m{s:.0f}s"
        else:
            h = t // 3600
            return f"{h:.0f}h{m:.0f}m{s:.0f}s"
