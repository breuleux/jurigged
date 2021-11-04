import builtins
from functools import partial
from types import SimpleNamespace

from giving import give, given

from .basic import BasicDeveloopRunner
from .develoop import Develoop, DeveloopRunner, RedirectDeveloopRunner
from .richloop import RichDeveloopRunner

loop = partial(Develoop, on_error=False, runner_class=RichDeveloopRunner)
loop_on_error = partial(
    Develoop, on_error=True, runner_class=RichDeveloopRunner
)
xloop = loop_on_error

__ = SimpleNamespace(
    loop=loop,
    loop_on_error=loop_on_error,
    xloop=xloop,
    give=give,
    given=given,
)


def inject():
    builtins.__ = __
