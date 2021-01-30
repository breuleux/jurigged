import os
import sys

import pytest

from jurigged import codefile
from jurigged.register import ImportSniffer, Registry, glob_filter

from .common import TemporaryModule, one_test_per_assert


def glob_test(pattern, file):
    return glob_filter(pattern)(file)


def rel(file):
    return os.path.abspath(file)


def user(file):
    return f"{os.getenv('HOME')}/{file}"


def clear_zy():
    for name in ["ya", "yb", "za", "zb"]:
        if name in sys.modules:
            del sys.modules[name]


@pytest.fixture
def tmod(scope="module"):
    return TemporaryModule()


@one_test_per_assert
def test_glob_filter():
    assert glob_test("*.py", rel("hello.py"))
    assert glob_test("./*.py", rel("hello.py"))

    assert glob_test("~/*.py", user("hello.py"))

    assert glob_test("/a/b/*.py", "/a/b/hello.py")
    assert glob_test("/a/b/*.py", "/a/b/c/hello.py")
    assert not glob_test("/a/b/*.py", "/b/hello.py")


def test_registry_prepare(tmod):
    mangle = "_1"
    log = []
    reg = Registry()

    tmod.transfer("ya", mangle=mangle)
    reg.prepare("ya_1", tmod.rel("ya_1.py"))  # Can prepare because file exists
    assert reg.get(tmod.rel("ya_1.py")) is None  # not imported yet
    import ya_1  # noqa

    # Should call lambda regarding the previous prepare(ya_1)
    reg.precache_activity.register(lambda *args: log.append(args))
    assert log == [("ya_1", tmod.rel("ya_1.py"))]

    tmod.imp("za", mangle=mangle)
    assert log == [("ya_1", tmod.rel("ya_1.py"))]

    sniff = reg.auto_register(glob_filter(tmod.rel("z*.py")))
    assert log == [("ya_1", tmod.rel("ya_1.py")), ("za_1", tmod.rel("za_1.py"))]

    tmod.imp("zb", mangle=mangle)
    assert log == [
        ("ya_1", tmod.rel("ya_1.py")),
        ("za_1", tmod.rel("za_1.py")),
        ("zb_1", tmod.rel("zb_1.py")),
    ]

    tmod.imp("yb", mangle=mangle)
    assert log == [
        ("ya_1", tmod.rel("ya_1.py")),
        ("za_1", tmod.rel("za_1.py")),
        ("zb_1", tmod.rel("zb_1.py")),
    ]
    sniff.uninstall()


def test_registry_get(tmod):
    mangle = "_2"
    log = []
    reg = Registry()
    sniff = reg.auto_register(glob_filter(tmod.rel("*.py")))
    reg.set_logger(lambda event: log.append(type(event)))

    assert reg.get(tmod.rel("za_2.py")) is None

    za = tmod.imp("za", mangle=mangle)
    assert za.word == "tyrant"

    cf = reg.get(tmod.rel("za_2.py"))
    assert reg.get(tmod.rel("za_2.py")) is cf
    tmod.write("za_2.py", 'word = "pirate"\n')
    cf.refresh()
    assert za.word == "pirate"

    assert log == [codefile.AddOperation, codefile.DeleteOperation]
    sniff.uninstall()


def _blah(x, y):
    def inner():
        return x + y

    return inner


def test_registry_find(tmod):
    mangle = "_3"
    reg = Registry()
    sniff = reg.auto_register(glob_filter(tmod.rel("*.py")))
    zb = tmod.imp("zb", mangle=mangle)

    cf, defn = reg.find_function(zb.quack)
    assert cf.filename == tmod.rel("zb_3.py")
    assert defn.object is zb.quack

    cf, defn = reg.find_function(_blah)
    assert cf.filename == __file__
    assert defn.object is _blah

    cf, defn = reg.find_function(_blah(3, 4))
    assert cf.filename == __file__
    assert defn is None

    assert reg.find_function(1234) == (None, None)

    assert reg.find("inexistent", 3) == (None, None)

    sniff.uninstall()


def test_registry_import_error(tmod):
    reg = Registry()
    sniff = reg.auto_register(glob_filter(tmod.rel("*.py")))

    with pytest.raises(ModuleNotFoundError):
        import so_unknown  # noqa

    sniff.uninstall()


def test_bad_sniffer(tmod):
    sniff = ImportSniffer(lambda *args: 1 / 0)
    sniff.install()

    za = tmod.imp("za", mangle="_4")
    assert za.word == "tyrant"
