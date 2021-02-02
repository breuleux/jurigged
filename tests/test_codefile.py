import inspect
import math
import os
import textwrap
from types import SimpleNamespace as NS

import pytest

from jurigged.codefile import CodeFile, Definition, StaleException, conform

from .common import TemporaryModule, one_test_per_assert
from .snippets import apple


class CodeFileCollection:
    def __init__(self, tmod, basename):
        self.tmod = tmod
        self.basename = basename
        self.variants = {
            name.split(".py")[0].split(":")[1]
            for name in os.listdir(
                os.path.join(os.path.dirname(__file__), "snippets")
            )
            if name.startswith(basename)
        }
        module = tmod.imp(f"{basename}:main")
        main_cf = CodeFile(module.__file__)
        main_cf.discover(module)

        self.module = module
        self.main = main_cf
        self.read_codefiles()

    def read_codefiles(self):
        files = {
            variant: self.module.__file__
            if variant == "main"
            else self.tmod.transfer(f"{self.basename}:{variant}")[1]
            for variant in self.variants
        }
        self.files = NS(**files)
        self.cf = NS(
            **{variant: CodeFile(file) for variant, file in files.items()}
        )

    def read(self, name="main"):
        path = getattr(self.files, name)
        with open(path) as f:
            return f.read()

    def write(self, name, contents):
        path = getattr(self.files, name)
        open(path, "w").write(contents)


@pytest.fixture
def tmod(scope="module"):
    return TemporaryModule()


def getsource(fn):
    return inspect.getsource(fn).rstrip()


def chk(codefile, name, l0, ln, fn, parent=None, src=None, nlock=0):
    funcs = codefile.defnmap
    if parent is not None:
        parent = funcs[parent[1]]
    if src is None:
        src = getsource(fn)
    indent = len(src) - len(src.lstrip())
    src = textwrap.dedent(src)
    fu = funcs[l0]
    return fu == Definition(
        type="function",
        name=name,
        filename=fu.filename,
        firstlineno=l0,
        lastlineno=ln,
        nlock=nlock,
        parent=parent,
        children=[],
        indent=indent,
        source=src,
        saved=src,
        live=src,
        node=None,  # not compared for equality
        object=fn,
    )


@pytest.fixture
def apple_file(scope="module"):
    cf = CodeFile(apple.__file__)
    cf.discover(apple)
    return cf


@pytest.fixture
def ballon(tmod):
    return CodeFileCollection(tmod, "ballon")


@pytest.fixture
def chips(tmod):
    return CodeFileCollection(tmod, "chips")


@pytest.fixture
def dandelion(tmod):
    return CodeFileCollection(tmod, "dandelion")


@pytest.fixture
def elephant(tmod):
    return CodeFileCollection(tmod, "elephant")


@pytest.fixture
def firmament(tmod):
    return CodeFileCollection(tmod, "firmament")


def f1(x):
    return x * 2


def f2(x):
    return x * 10


def test_conform():
    ff1 = f1
    ff2 = f2

    # Should make the behavior of the two functions equal
    assert ff1(4) == 8
    assert ff2(4) == 40
    conform(f1, f2)
    assert ff1(4) == 40
    assert ff2(4) == 40
    assert ff1.__code__ is ff2.__code__

    # Should not crash on non-functions
    conform(1, 2)


@one_test_per_assert
def test_codefile(apple_file):
    assert chk(apple_file, "crunch", 1, 3, apple.crunch)
    assert chk(apple_file, "breakfast", 6, 10, apple.breakfast, nlock=3)
    assert chk(
        apple_file,
        "cortland",
        23,
        26,
        apple.Orchard.cortland,
        parent=("Orchard", 13),
    )
    assert chk(
        apple_file,
        "honeycrisp",
        18,
        21,
        apple.Orchard.honeycrisp.__func__,
        parent=("Orchard", 13),
        nlock=1,
    )
    assert chk(
        apple_file,
        "mcintosh",
        14,
        16,
        apple.Orchard.mcintosh,
        parent=("Orchard", 13),
        nlock=1,
    )
    assert chk(apple_file, "juggle", 29, 33, apple.juggle)
    assert chk(apple_file, "pomme", 36, 39, apple.pomme)
    assert chk(
        apple_file, "pommier", 52, 54, apple.pommier.__wrapped__, nlock=1
    )
    assert chk(
        apple_file,
        "color",
        58,
        60,
        apple.FakeApple.color.fget,
        parent=("FakeApple", 57),
        nlock=1,
    )
    assert chk(
        apple_file,
        "color",
        62,
        64,
        apple.FakeApple.color.fset,
        parent=("FakeApple", 57),
        nlock=1,
    )
    # assert chk(
    #     apple_file,
    #     "ver",
    #     37,
    #     38,
    #     None,
    #     parent=("pomme", 36),
    #     src='    def ver():\n        return "nyah ha ha ha"',
    # )


def test_match_definitions(ballon):
    bmod = ballon.module
    ba = ballon.main
    bb = ballon.cf.v2

    same, changes, adds, dels = ba.match_definitions(bb)

    assert all(x.name == y.name for x, y in same)
    assert all(x.name == y.name for x, y in changes)

    same_info = {
        (x.name, x.firstlineno, y.firstlineno, x.object) for x, y in same
    }
    changes_info = {
        (x.name, x.firstlineno, y.firstlineno, x.object) for x, y in changes
    }
    adds = {x.name for x in adds}
    dels = {x.name for x in dels}

    assert same_info == {
        (None, 1, 1, None),
        ("__init__", 9, 5, bmod.Sphere.__init__),
        ("volume", 12, 8, bmod.Sphere.volume),
        ("__init__", 17, 17, bmod.FlatCircle.__init__),
        ("Sphere", 8, 4, bmod.Sphere),
        ("FlatCircle", 16, 16, bmod.FlatCircle),
    }
    assert changes_info == {
        ("inflate", 4, 12, bmod.inflate),
        ("volume", 23, 23, bmod.FlatCircle.volume),
    }
    assert adds == {"circumference", "deflate"}
    assert dels == {"uninteresting", "unsightly"}


def test_merge(ballon):
    radius = 10
    cir = ballon.module.FlatCircle(radius)
    inflate = ballon.module.inflate
    volume = cir.volume

    # Initial definitions
    assert ballon.module.inflate(5) == 10
    assert inflate(5) == 10
    assert cir.volume() == -1
    assert volume() == -1
    assert cir.unsightly() == "yuck"
    with pytest.raises(AttributeError):
        cir.circumference()
    assert ballon.module.uninteresting() is None

    # Merge the new code
    ballon.main.merge(ballon.cf.v2)

    # New definitions should be active
    assert ballon.module.inflate(5) == 15
    assert inflate(5) == 15
    assert ballon.module.deflate(15) == 5
    assert cir.volume() == 0
    assert volume() == 0
    with pytest.raises(AttributeError):
        cir.unsightly()
    assert cir.circumference() == 2 * math.pi * radius
    with pytest.raises(AttributeError):
        ballon.module.uninteresting()


def test_merge_partial(ballon):
    radius = 10
    cir = ballon.module.FlatCircle(radius)

    assert cir.volume() == -1
    assert cir.unsightly() == "yuck"
    ballon.main.merge(ballon.cf.v2, deletable=False)
    assert cir.volume() == 0
    assert cir.unsightly() == "yuck"


def test_merge_back_and_forth(ballon):
    radius = 10
    cir = ballon.module.FlatCircle(radius)
    inflate = ballon.module.inflate
    volume = cir.volume

    def _initial():
        # Initial definitions
        assert ballon.module.inflate(5) == 10
        assert inflate(5) == 10
        assert cir.volume() == -1
        assert volume() == -1
        assert cir.unsightly() == "yuck"
        with pytest.raises(AttributeError):
            cir.circumference()
        assert ballon.module.uninteresting() is None

    def _new():
        # New definitions should be active
        assert ballon.module.inflate(5) == 15
        assert inflate(5) == 15
        assert ballon.module.deflate(15) == 5
        assert cir.volume() == 0
        assert volume() == 0
        with pytest.raises(AttributeError):
            cir.unsightly()
        assert cir.circumference() == 2 * math.pi * radius
        with pytest.raises(AttributeError):
            ballon.module.uninteresting()

    _initial()
    # We must re-read the codefiles each time because the definitions
    # may be modified by merge.
    ballon.read_codefiles()
    ballon.main.merge(ballon.cf.v2)
    _new()
    ballon.read_codefiles()
    ballon.main.merge(ballon.cf.main)
    _initial()
    ballon.read_codefiles()
    ballon.main.merge(ballon.cf.v2)
    _new()
    ballon.read_codefiles()
    ballon.main.merge(ballon.cf.main)
    _initial()
    ballon.read_codefiles()
    ballon.main.merge(ballon.cf.v2)
    _new()


def test_merge_decorators(chips):
    assert chips.module.munch(4) == 6
    chips.main.merge(chips.cf.mod, deletable=False)
    assert chips.module.munch(4, 2) == 8


def test_merge_decorators_fail(chips):
    assert chips.module.munch(4) == 6
    chips.main.merge(chips.cf.bad, deletable=False)
    assert chips.module.munch(4) == 6


def test_commit_noop(dandelion):
    orig = dandelion.read()
    dandelion.main.commit()
    assert dandelion.read() == orig


def test_commit(dandelion):
    orig = dandelion.read()
    dandelion.main.merge(dandelion.cf.v2)
    assert dandelion.read() == orig
    dandelion.main.commit()
    print(dandelion.read().strip())
    assert dandelion.read().strip() == dandelion.read("v2result").strip()


def test_commit_partial(dandelion):
    orig = dandelion.read()
    dandelion.main.merge(dandelion.cf.repl, deletable=False)
    assert dandelion.read() == orig
    dandelion.main.commit()
    assert dandelion.read() == dandelion.read("outcome")


def test_commit_partial_2(dandelion):
    orig = dandelion.read()
    dandelion.main.merge(
        dandelion.cf.repl,
        deletable=[dandelion.main.locate(dandelion.module.plack)],
    )
    assert dandelion.read() == orig
    dandelion.main.commit()
    assert dandelion.read() == dandelion.read("outcome2")


def test_commit_stale(dandelion):
    dandelion.main.merge(dandelion.cf.v2)
    open(dandelion.main.filename, "w").write("")
    with pytest.raises(StaleException):
        dandelion.main.commit()


def test_functions_interface(elephant):
    do = elephant.module.do
    assert do(7) == ["Paint 7 canvasses", "Sing 7 songs", "Dance for 7 hours"]
    elephant.main.merge(elephant.cf.mod)
    assert do(7) == ["Paint 7 canvasses", "Sing 14 songs", "Dance for 7 hours"]


def test_functions_interface_add(elephant):
    do = elephant.module.do
    assert do(7) == ["Paint 7 canvasses", "Sing 7 songs", "Dance for 7 hours"]
    elephant.main.merge(elephant.cf.more)
    assert do(7) == [
        "Paint 7 canvasses",
        "Sing 7 songs",
        "Worship the 7 suns",
        "Dance for 7 hours",
        "Do 7 push-ups",
    ]


def test_functions_interface_rm(elephant):
    do = elephant.module.do
    assert do(7) == ["Paint 7 canvasses", "Sing 7 songs", "Dance for 7 hours"]
    elephant.main.merge(elephant.cf.less)
    assert do(7) == ["Eat 7 bananas"]


def test_update_statements(firmament):
    assert firmament.module.sirius(5) == 25
    firmament.module.ursa_major.append(888)
    assert firmament.module.betelgeuse == 1000

    firmament.main.merge(firmament.cf.mod)

    assert firmament.module.sirius(5) == 3
    # Does not re-run the ursa_major assignment because it did not change
    assert firmament.module.ursa_major == [1, 2, 3, 4, 888]
    # Re-runs betelgeuse assignment
    assert firmament.module.betelgeuse == 41


def test_regen_statements(firmament):
    firmament.main.merge(firmament.cf.mod)
    firmament.main.commit()
    print(firmament.read().strip())
    assert firmament.read().strip() == firmament.read("result").strip()


def test_predecessor(ballon):
    vol = ballon.main.locate(ballon.module.FlatCircle.volume)
    uns = ballon.main.locate(ballon.module.FlatCircle.unsightly)
    init = ballon.main.locate(ballon.module.FlatCircle.__init__)
    assert vol.predecessor(vol.filename) is uns

    ballon.main.merge(ballon.cf.v2)
    assert vol.predecessor(vol.filename) is not uns
    assert vol.predecessor(vol.filename) is init


def test_successor(ballon):
    vol = ballon.main.locate(ballon.module.FlatCircle.volume)
    uns = ballon.main.locate(ballon.module.FlatCircle.unsightly)
    init = ballon.main.locate(ballon.module.FlatCircle.__init__)
    assert init.successor(vol.filename) is uns

    ballon.main.merge(ballon.cf.v2)
    assert init.successor(vol.filename) is not uns
    assert init.successor(vol.filename) is vol
