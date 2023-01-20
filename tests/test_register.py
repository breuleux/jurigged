import os
import sys
import types

import pytest

from jurigged import codetools
from jurigged.register import Registry, add_sniffer, glob_filter

from . import common
from .common import TemporaryModule, _blah, one_test_per_assert


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
    assert glob_test(".", rel("hello.py"))
    assert glob_test("./", rel("hello.py"))

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

    assert log == [
        codetools.AddOperation,
        codetools.DeleteOperation,
        codetools.UpdateOperation,
    ]
    sniff.uninstall()


def test_registry_find(tmod):
    mangle = "_3"
    reg = Registry()
    sniff = reg.auto_register(glob_filter(tmod.rel("*.py")))
    zb = tmod.imp("zb", mangle=mangle)

    cf, defn = reg.find(zb.quack)
    assert cf.filename == tmod.rel("zb_3.py")
    assert defn.get_object() is zb.quack.__code__

    cf, defn = reg.find(zb.Duck)
    assert cf.filename == tmod.rel("zb_3.py")
    assert defn.get_object() is zb.Duck

    cf, defn = reg.find(zb.Duck.quack)
    assert cf.filename == tmod.rel("zb_3.py")
    assert defn.get_object() is zb.Duck.quack.__code__

    cf, defn = reg.find(_blah.__code__)
    assert cf.filename == common.__file__
    assert defn.get_object() is _blah.__code__

    cf, defn = reg.find(_blah)
    assert cf.filename == common.__file__
    assert defn.get_object() is _blah.__code__

    # Trigger the cached entry for filename -> module_name
    cf, defn = reg.find(glob_filter.__code__)
    assert "jurigged/utils.py" in cf.filename
    assert defn.get_object() is glob_filter.__code__

    cf, defn = reg.find(_blah(3, 4))
    assert cf.filename == common.__file__
    assert defn is not None

    with pytest.raises(TypeError):
        reg.find(1234)

    assert reg.get_at("inexistent", 3) == (None, None)

    sniff.uninstall()


def test_registry_cannot_find(tmod):
    reg = Registry()
    typ = type("Generated", (object,), {})
    cf, defn = reg.find(typ)
    assert cf.filename == __file__
    assert defn is None

    fn = types.FunctionType(
        _blah.__code__.replace(co_name="xxx", co_firstlineno=10000), {}
    )
    cf, defn = reg.find(fn)
    assert cf.filename == common.__file__
    assert defn is None


def test_registry_import_error(tmod):
    reg = Registry()
    sniff = reg.auto_register(glob_filter(tmod.rel("*.py")))

    with pytest.raises(ModuleNotFoundError):
        import so_unknown  # noqa

    sniff.uninstall()


def test_bad_sniffer(tmod):
    sniff = add_sniffer(lambda *args: 1 / 0)

    za = tmod.imp("za", mangle="_4")
    assert za.word == "tyrant"

    sniff.uninstall()
