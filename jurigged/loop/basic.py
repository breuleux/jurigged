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
                ch = sys.stdin.read(1)
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
