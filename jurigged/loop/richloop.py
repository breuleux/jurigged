import re
import sys
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass

import rx
from giving import ObservableProxy
from pygments import token
from rich._loop import loop_last
from rich.cells import cell_len
from rich.console import Console, Group
from rich.constrain import Constrain
from rich.highlighter import ReprHighlighter
from rich.live import Live
from rich.markup import render as markup
from rich.panel import Panel
from rich.pretty import Pretty
from rich.segment import Segment
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.traceback import Traceback

from .basic import ANSI_ESCAPE, cbreak, read_chars, readable_duration
from .develoop import RedirectDeveloopRunner, itemappender, kill_thread

REAL_STDOUT = sys.stdout
TEMP_CONSOLE = Console(color_system="standard")


class TracebackNoFrame(Traceback):
    """Variant of rich.traceback.Traceback that does not draw a frame around the traceback."""

    def __rich_console__(self, console, options):
        # I basically just copied this from https://github.com/willmcgugan/rich/blob/master/rich/traceback.py
        # and removed calls to Panel
        theme = self.theme
        token_style = theme.get_style_for_token

        traceback_theme = Theme(
            {
                "pretty": token_style(token.Text),
                "pygments.text": token_style(token.Token),
                "pygments.string": token_style(token.String),
                "pygments.function": token_style(token.Name.Function),
                "pygments.number": token_style(token.Number),
                "repr.indent": token_style(token.Comment) + Style(dim=True),
                "repr.str": token_style(token.String),
                "repr.brace": token_style(token.Text) + Style(bold=True),
                "repr.number": token_style(token.Number),
                "repr.bool_true": token_style(token.Keyword.Constant),
                "repr.bool_false": token_style(token.Keyword.Constant),
                "repr.none": token_style(token.Keyword.Constant),
                "scope.border": token_style(token.String.Delimiter),
                "scope.equals": token_style(token.Operator),
                "scope.key": token_style(token.Name),
                "scope.key.special": token_style(token.Name.Constant)
                + Style(dim=True),
            }
        )

        highlighter = ReprHighlighter()
        for last, stack in loop_last(reversed(self.trace.stacks)):
            if stack.frames:
                stack_renderable = self._render_stack(stack)
                stack_renderable = Constrain(stack_renderable, self.width)
                with console.use_theme(traceback_theme):
                    yield stack_renderable
            if stack.syntax_error is not None:
                with console.use_theme(traceback_theme):
                    yield Constrain(
                        self._render_syntax_error(stack.syntax_error)
                    )
                yield Text.assemble(
                    (f"{stack.exc_type}: ", "traceback.exc_type"),
                    highlighter(stack.syntax_error.msg),
                )
            elif stack.exc_value:
                yield Text.assemble(
                    (f"{stack.exc_type}: ", "traceback.exc_type"),
                    highlighter(stack.exc_value),
                )
            else:
                yield Text.assemble((f"{stack.exc_type}", "traceback.exc_type"))

            if not last:
                if stack.is_cause:
                    yield Text.from_markup(
                        "\n[i]The above exception was the direct cause of the following exception:\n",
                    )
                else:
                    yield Text.from_markup(
                        "\n[i]During handling of the above exception, another exception occurred:\n",
                    )


class RawSegment(Segment):
    @property
    def cell_length(self):
        assert not self.control
        return cell_len(re.sub(ANSI_ESCAPE, "", self.text))


@dataclass
class Line:
    text: str = ""
    length: int = 0

    def __bool__(self):
        return bool(self.text)


def breakline(line, limit=80, initial=Line()):
    if not line:
        yield initial
        return

    parts = [
        (x, i % 2 == 1)
        for i, x in enumerate(re.split(pattern=ANSI_ESCAPE, string=line))
    ]
    current_line = initial.text
    avail = limit - initial.length
    work = deque(parts)
    while work:
        part, escape = work.popleft()
        if escape:
            current_line += part
        else:
            if not avail:
                ok, extra = "", part
            else:
                ok, extra = part[:avail], part[avail:]
            avail -= len(ok)
            current_line += ok
            if extra:
                work.appendleft((extra, False))
                yield Line(current_line, limit - avail)
                current_line = ""
                avail = limit
    if current_line:
        yield Line(current_line, limit - avail)


class TerminalLines:
    def __init__(self, title, border="white", border_highlight="bold yellow"):
        self.title = title
        self.border = border
        self.border_highlight = border_highlight
        self.height = 0
        self.width = 80
        self.window_size = 1
        self.clear()

    def set_at_end(self):
        self.at_end = self.start >= (len(self) - self.window_size)

    def add(self, text):
        line1, *lines = text.split("\n")
        self.lines[-1:] = breakline(
            line1, limit=self.width, initial=self.lines[-1]
        )
        for line in lines:
            self.lines += breakline(line, limit=self.width)
        return self

    def clear(self):
        self.lines = [Line()]
        self.start = 0
        self.at_end = True

    def shift(self, n, mode):
        if mode == "line":
            self.start = max(0, self.start + n)
        elif mode == "screen":
            self.start = max(0, self.start + n * self.window_size)
        elif mode == "whole":
            self.start = max(0, self.start + n * len(self))
        self.set_at_end()

    def __len__(self):
        # We don't count the last line if it is empty
        return len(self.lines) - 1 + bool(self.lines[-1])

    def __rich_console__(self, console, options):
        if self.at_end:
            self.start = len(self)
        self.start = max(0, min(self.start, len(self) - self.window_size))
        for i, line in enumerate(self.lines[self.start : len(self)]):
            yield RawSegment(line.text)
            if i < len(self) - 1:
                yield Segment.line()

    __iadd__ = add


class StackedTerminalLines:
    def __init__(self, boxes, total_height, width):
        self.boxes = boxes
        for b in self.boxes:
            b.width = width
        self.box_map = {b.title: b for b in self.boxes}
        self.total_height = total_height
        self.width = width
        self.focus = None

    def __getitem__(self, item):
        return self.box_map[item]

    def __setitem__(self, item, value):
        pass

    def clear(self):
        for b in self.boxes:
            b.clear()

    def move_focus(self, n):
        nb = len(self.boxes)
        old_focus = self.focus or 0
        explore = [(i + n + old_focus + nb) % nb for i in range(nb + 1)]
        if n < 0:
            explore.reverse()
        for focus in explore:
            if self.boxes[focus]:
                break
        self.focus = focus

    def shift(self, n, mode):
        self.focus = self.focus or 0
        self.boxes[self.focus].shift(n, mode=mode)

    def distribute_heights(self):
        budget = self.total_height
        boxes = self.boxes
        max_height = max(len(b) for b in boxes)
        nactive = len([b for b in boxes if b])
        if nactive == 0:
            return
        max_share = budget // nactive
        for i, b in enumerate(boxes):
            b.height = h = min(max_share, len(b) + 2) if b else 0
            if self.focus is None and len(b) > max_share:
                self.focus = i
            budget -= h
        if budget:
            for b in boxes:
                if len(b) == max_height:
                    b.height += budget
                    break
        for b in boxes:
            b.window_size = b.height - 2

    def __rich_console__(self, console, options):
        self.distribute_heights()
        for i, box in enumerate(self.boxes):
            if box.height:
                if i == self.focus:
                    title = f"[bold]{box.title}"
                    style = box.border_highlight
                else:
                    title = box.title
                    style = box.border
                yield Panel(
                    box, title=title, height=box.height, border_style=style
                )


class Dash:
    def __init__(self, *parts):
        self.console = Console(color_system="standard", file=REAL_STDOUT)
        self.lv = Live(
            auto_refresh=False,
            redirect_stdout=False,
            redirect_stderr=False,
            console=self.console,
            screen=True,
        )
        self.stack = StackedTerminalLines(
            parts, self.lv.console.height - 2, width=self.lv.console.width - 4
        )
        self.header = Text("<header>")
        self.footer = Text("<footer>")

    def clear(self):
        self.stack.clear()
        self.header = Text("<header>")
        self.footer = Text("<footer>")

    def shifter(self, n, mode):
        def shift(_=None):
            if mode == "line":
                self.stack.shift(n, mode="line")
            elif mode == "screen":
                self.stack.shift(n, mode="screen")
            elif mode == "whole":
                self.stack.shift(n, mode="whole")
            elif mode == "focus":
                self.stack.move_focus(n)
            else:
                raise Exception(f"Unknown mode: {mode}")
            self.update()

        return shift

    def update(self):
        self.lv.update(
            Group(self.header, self.stack, self.footer), refresh=True
        )

    def run(self):
        return self.lv


class RichDeveloopRunner(RedirectDeveloopRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dash = Dash(
            TerminalLines(title="stdout"),
            TerminalLines(
                title="stderr", border="red", border_highlight="bold red"
            ),
            TerminalLines(title="given"),
            TerminalLines(
                title="error", border="red", border_highlight="bold red"
            ),
            TerminalLines(
                title="result", border="cyan", border_highlight="bold cyan"
            ),
        )

    def _update(self):
        wall = (
            f" in {readable_duration(self._walltime)}" if self._walltime else ""
        )
        footer = [
            f"#{self.num} ({self._status}{wall})",
            "[bold](c)[/bold]ontinue",
            "[bold](r)[/bold]erun",
            (not self._has_result and not self._has_error)
            and "[bold](a)[/bold]bort",
            "[bold](q)[/bold]uit",
        ]
        self.dash.header = markup(f"Looping on: [bold]{self.signature()}")
        self.dash.footer = markup(" | ".join(x for x in footer if x))

        if self._gvn:
            self.dash.stack["given"].clear()
            table = Table.grid(padding=(0, 3, 0, 0))
            table.add_column("key", style="bold green")
            table.add_column("value")
            for k, v in self._gvn.items():
                table.add_row(k, Pretty(v))
            with TEMP_CONSOLE.capture() as cap:
                TEMP_CONSOLE.print(table)
            self.dash.stack["given"].add(cap.get())

        self.dash.update()

    @contextmanager
    def wrap_loop(self):
        with self.dash.run(), cbreak():
            try:
                scheduler = rx.scheduler.EventLoopScheduler()
                kp = ObservableProxy(
                    rx.from_iterable(read_chars(), scheduler=scheduler)
                ).share()

                kp.where(char="c") >> self.command("cont")
                kp.where(char="r") >> self.command("go", aborts=True)
                kp.where(char="a") >> self.command("abort", aborts=True)
                kp.where(char="q") >> self.command("quit", aborts=True)

                # Up
                kp.where(char="[A") >> self.dash.shifter(-1, mode="line")
                # Down
                kp.where(char="[B") >> self.dash.shifter(1, mode="line")

                # Page Up
                kp.where(char="[5~") >> self.dash.shifter(-1, mode="screen")
                # Page Down
                kp.where(char="[6~") >> self.dash.shifter(1, mode="screen")

                # Home
                kp.where(char="[1~") >> self.dash.shifter(-1, mode="whole")
                # End
                kp.where(char="[4~") >> self.dash.shifter(1, mode="whole")

                # Left
                kp.where(char="[D") >> self.dash.shifter(-1, mode="focus")
                # Right
                kp.where(char="[C") >> self.dash.shifter(1, mode="focus")

                yield

            finally:
                kill_thread(scheduler._thread)
                scheduler.dispose()

    def register_updates(self, gv):
        self.dash.clear()
        self._has_result = False
        self._has_error = False
        self._status = "running"
        self._walltime = 0
        self._gvn = {}

        # Append stdout/stderr incrementally
        gv["?#stdout"] >> itemappender(self.dash.stack, "stdout")
        gv["?#stderr"] >> itemappender(self.dash.stack, "stderr")

        def _on(key):
            # black and vscode's syntax highlighter both choke on parsing the following
            # as a decorator, that's why I made a function
            return gv.getitem(key, strict=False).subscribe

        @_on("#result")
        def _(result):
            with TEMP_CONSOLE.capture() as cap:
                TEMP_CONSOLE.print(result)
            self.dash.stack["result"].add(cap.get())
            self._has_result = True

        @_on("#error")
        def _(error):
            tb = TracebackNoFrame(
                trace=TracebackNoFrame.extract(
                    type(error), error, error.__traceback__
                ),
            )
            with TEMP_CONSOLE.capture() as cap:
                TEMP_CONSOLE.print(tb)
            self.dash.stack["error"].add(cap.get())
            self._has_error = True

        @_on("#status")
        def _(status):
            self._status = status

        @_on("#walltime")
        def _(walltime):
            self._walltime = walltime

        # Fill given table
        @gv.subscribe
        def _(d):
            self._gvn.update(
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
            lambda _: self._update()
        )

        self._update()
