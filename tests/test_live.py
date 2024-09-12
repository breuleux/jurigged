import builtins
import time

from jurigged import codetools
from jurigged.live import (
    WatchOperation,
    conservative_logger as conlog,
    default_logger,
    to_filter,
    watch,
)
from jurigged.register import Registry

from .common import catalogue, one_test_per_assert
from .test_codetools import apple_code as apple, tmod as tmod  # noqa

pause = 0.05


def _capture(obj, logger=default_logger):
    value = []
    old_print = print
    builtins.print = lambda *args: value.append(" ".join(map(str, args)))
    logger(obj)
    builtins.print = old_print
    return "\n".join(value)


def _std(
    cls, cf, lineno, logger=default_logger, defntype="FunctionDefinition", **kw
):
    return _capture(
        cls(
            codefile=cf,
            defn=catalogue(cf.root)[defntype, cf.filename, lineno],
            **kw,
        ),
        logger=logger,
    )


@one_test_per_assert
def test_logger(apple):
    assert (
        _std(codetools.UpdateOperation, apple, 23)
        == "Update tests.snippets.apple.Orchard.cortland @L23"
    )
    assert (
        _std(codetools.AddOperation, apple, 23)
        == "Add tests.snippets.apple.Orchard.cortland @L23"
    )
    assert (
        _std(codetools.AddOperation, apple, 42, defntype="LineDefinition")
        == "Run tests.snippets.apple @L42: from functools import wraps"
    )
    assert (
        _std(codetools.DeleteOperation, apple, 23)
        == "Delete tests.snippets.apple.Orchard.cortland @L23"
    )
    assert _capture(WatchOperation("some_file.py")) == "Watch some_file.py"
    assert "TypeError" in _capture(TypeError("hello"))
    assert "SyntaxError" in _capture(SyntaxError("oh no"))
    assert _capture(12345) == "12345"


@one_test_per_assert
def test_conservative_logger(apple):
    assert _capture(TypeError("hello"), logger=conlog) == _capture(
        TypeError("hello")
    )
    assert _capture(SyntaxError("oh no"), logger=conlog) == _capture(
        SyntaxError("oh no")
    )
    assert _capture(SyntaxError("oh no"), logger=conlog) == _capture(
        SyntaxError("oh no")
    )
    assert _std(codetools.DeleteOperation, apple, 23, logger=conlog) == ""


def test_watch(tmod):
    mangle = "_5"
    registry = Registry()
    watcher = watch(pattern=tmod.rel("*.py"), registry=registry, debounce=0)
    za = tmod.imp("za", mangle=mangle)
    assert za.word == "tyrant"

    # This one is a syntax error, but it shouldn't kill the thread
    tmod.write("za_5.py", 'word = "pirate\n')
    # If the FS is slow 0.05 seconds might not be enough, but oh well
    time.sleep(pause)
    assert za.word == "tyrant"

    # This one is OK and the change should be loaded
    tmod.write("za_5.py", 'word = "pirate"\n')
    time.sleep(pause)
    assert za.word == "pirate"

    watcher.stop()
    # Updates won't reload anymore
    tmod.write("za_5.py", 'word = "nowatch"\n')
    time.sleep(pause)
    assert za.word == "pirate"

    watcher.join()
    assert not watcher.observer.is_alive()


def test_debounce(tmod):
    def lg(evt):
        evts.append(type(evt).__name__)

    evts = []
    mangle = "_6"
    registry = Registry()
    watch(pattern=tmod.rel("*.py"), registry=registry, debounce=0.1)
    registry.activity.register(lg)

    za = tmod.imp("za", mangle=mangle)
    assert za.word == "tyrant"

    tmod.write("za_6.py", "")
    time.sleep(pause)
    tmod.write("za_6.py", 'word = "tyrant"\nxxx = "xxx"')
    time.sleep(0.20)
    assert za.word == "tyrant"
    assert za.xxx == "xxx"

    assert evts.count("DeleteOperation") == 0
    assert evts.count("AddOperation") == 1
    assert evts.count("UpdateOperation") == 1


def test_poll(tmod):
    def lg(evt):
        evts.append(type(evt).__name__)

    evts = []
    mangle = "_7"
    registry = Registry()
    watch(pattern=tmod.rel("*.py"), registry=registry, poll=0.1)
    registry.activity.register(lg)

    za = tmod.imp("za", mangle=mangle)
    assert za.word == "tyrant"

    tmod.write("za_7.py", "")
    time.sleep(pause)
    tmod.write("za_7.py", 'word = "tyrant"\nxxx = "xxx"')
    time.sleep(0.10)
    assert za.word == "tyrant"
    assert za.xxx == "xxx"

    assert evts.count("DeleteOperation") == 0
    assert evts.count("AddOperation") == 1
    assert evts.count("UpdateOperation") == 1


def test_prerun(tmod):
    test_var = 0

    def prerun_test(path, cf):
        nonlocal test_var
        test_var += 1

    mangle = "_8"
    registry = Registry()

    pre_watcher = watch(
        pattern=tmod.rel("*.py"),
        registry=registry,
        debounce=0,
    )
    pre_watcher.prerun.register(prerun_test)
    za = tmod.imp("za", mangle=mangle)
    assert za.word == "tyrant"

    tmod.write("za_8.py", 'word = "pirate"\n')
    time.sleep(pause)
    assert test_var == 1

    pre_watcher.prerun.register(prerun_test)

    tmod.write("za_8.py", 'word = "tyrant"\n')
    time.sleep(pause)
    assert test_var == 3

    pre_watcher.stop()
    pre_watcher.join()


def test_postrun(tmod):
    test_var = 0

    def postrun_test(path, cf):
        nonlocal test_var
        test_var += 1

    mangle = "_9"
    registry = Registry()

    post_watcher = watch(
        pattern=tmod.rel("*.py"),
        registry=registry,
        debounce=0,
    )
    post_watcher.postrun.register(postrun_test)
    za = tmod.imp("za", mangle=mangle)
    assert za.word == "tyrant"

    tmod.write("za_9.py", 'word = "tyrant"\n')
    time.sleep(pause)
    assert test_var == 1

    post_watcher.postrun.register(postrun_test)

    tmod.write("za_9.py", 'word = "pirate"\n')
    time.sleep(pause)
    assert test_var == 3

    post_watcher.stop()
    post_watcher.join()


def test_prerun_postrun(tmod):
    test_var = 0

    def prerun_test(path, cf):
        nonlocal test_var
        test_var += 1

    def postrun_test(path, cf):
        nonlocal test_var
        test_var += 2

    mangle = "_10"
    registry = Registry()

    both_watcher = watch(
        pattern=tmod.rel("*.py"),
        registry=registry,
        debounce=0,
    )
    both_watcher.prerun.register(prerun_test)
    both_watcher.postrun.register(postrun_test)

    za = tmod.imp("za", mangle=mangle)
    assert za.word == "tyrant"

    tmod.write("za_10.py", 'word = "pirate"\n')
    time.sleep(pause)
    assert test_var == 3

    both_watcher.prerun.register(prerun_test)
    both_watcher.postrun.register(postrun_test)

    tmod.write("za_10.py", 'word = "tyrant"\n')
    time.sleep(pause)
    assert test_var == 9

    both_watcher.stop()
    both_watcher.join()


def test_watch_multiple(tmod):
    mangle = "_11"
    registry = Registry()
    watcher = watch(
        pattern=[tmod.rel("za_11.py"), tmod.rel("ya_11.py")],
        registry=registry,
        debounce=0,
    )

    za = tmod.imp("za", mangle=mangle)
    assert za.word == "tyrant"

    # The change should be loaded
    tmod.write("za_11.py", 'word = "pirate"\n')
    time.sleep(pause)
    assert za.word == "pirate"

    ya = tmod.imp("ya", mangle=mangle)
    assert ya.word == "banana"

    # The change should be loaded
    tmod.write("ya_11.py", 'word = "cherry"\n')
    time.sleep(pause)
    assert ya.word == "cherry"

    yb = tmod.imp("yb", mangle=mangle)
    assert yb.word == "karate"

    # The change should NOT be loaded
    tmod.write("yb_11.py", 'word = "judo"\n')
    time.sleep(pause)
    assert yb.word == "karate"

    watcher.stop()
    watcher.join()
    assert not watcher.observer.is_alive()


def test_to_filter_coverage(tmod):
    def filt(x):
        return x.endswith(".py")

    assert to_filter(filt) is filt
    assert to_filter([filt]) is filt
