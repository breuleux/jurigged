import math
import os
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from codefind import code_registry as codereg

from jurigged.codetools import CodeFile, StaleException

from .common import TemporaryModule, catalogue
from .snippets import apple


class CodeCollection:
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
        main_cf = CodeFile(module.__file__, module.__name__)
        main_cf.associate(module)

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
            **{
                variant: CodeFile(file, self.module.__name__)
                for variant, file in files.items()
            }
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


@pytest.fixture
def apple_code(scope="module"):
    cf = CodeFile(apple.__file__, apple.__name__)
    cf.associate(apple)
    return cf


@pytest.fixture
def ballon(tmod):
    return CodeCollection(tmod, "ballon")


@pytest.fixture
def chips(tmod):
    return CodeCollection(tmod, "chips")


@pytest.fixture
def dandelion(tmod):
    return CodeCollection(tmod, "dandelion")


@pytest.fixture
def elephant(tmod):
    return CodeCollection(tmod, "elephant")


@pytest.fixture
def firmament(tmod):
    return CodeCollection(tmod, "firmament")


@pytest.fixture
def glamour(tmod):
    return CodeCollection(tmod, "glamour")


@pytest.fixture
def iguana(tmod):
    return CodeCollection(tmod, "iguana")


@pytest.fixture
def jackfruit(tmod):
    return CodeCollection(tmod, "jackfruit")


@pytest.fixture
def kilroy(tmod):
    return CodeCollection(tmod, "kilroy")


def test_collect(apple_code):
    cat = {
        f"{k[0]}@{k[2]}" if isinstance(k, tuple) else k: obj
        for k, v in catalogue(apple_code.root).items()
        if (obj := v.get_object()) is not None
    }
    assert cat == {
        "FunctionDefinition@1": apple.crunch.__code__,
        "FunctionDefinition@6": apple.breakfast.__code__,
        "FunctionDefinition@23": apple.Orchard.cortland.__code__,
        "ClassDefinition@13": apple.Orchard,
        "FunctionDefinition@14": apple.Orchard.mcintosh.__code__,
        "FunctionDefinition@18": apple.Orchard.honeycrisp.__func__.__code__,
        "FunctionDefinition@29": apple.juggle.__code__,
        "FunctionDefinition@36": apple.pomme.__code__,
        "FunctionDefinition@37": apple.pomme().__code__,
        "FunctionDefinition@45": apple.arbre.__code__,
        "FunctionDefinition@46": apple.pommier.__code__,
        "FunctionDefinition@52": apple.pommier.__wrapped__.__code__,
        "ClassDefinition@57": apple.FakeApple,
        "FunctionDefinition@58": apple.FakeApple.color.fget.__code__,
        "FunctionDefinition@62": apple.FakeApple.color.fset.__code__,
        "tests.snippets.apple.crunch": apple.crunch.__code__,
        "tests.snippets.apple.breakfast": apple.breakfast.__code__,
        "tests.snippets.apple.Orchard.cortland": apple.Orchard.cortland.__code__,
        "tests.snippets.apple.Orchard": apple.Orchard,
        "tests.snippets.apple.Orchard.mcintosh": apple.Orchard.mcintosh.__code__,
        "tests.snippets.apple.Orchard.honeycrisp": apple.Orchard.honeycrisp.__func__.__code__,
        "tests.snippets.apple.juggle": apple.juggle.__code__,
        "tests.snippets.apple.pomme": apple.pomme.__code__,
        "tests.snippets.apple.pomme.ver": apple.pomme().__code__,
        "tests.snippets.apple.arbre": apple.arbre.__code__,
        "tests.snippets.apple.arbre.branche": apple.pommier.__code__,
        "tests.snippets.apple.pommier": apple.pommier.__wrapped__.__code__,
        "tests.snippets.apple.FakeApple": apple.FakeApple,
        "tests.snippets.apple.FakeApple.color": apple.FakeApple.color.fset.__code__,
    }


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
    ballon.main.merge(ballon.cf.v2, allow_deletions=False)
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
    chips.main.merge(chips.cf.mod, allow_deletions=False)
    assert chips.module.munch(4, 2) == 8


def test_merge_decorators_change(chips):
    assert chips.module.munch(4) == 6
    chips.main.merge(chips.cf.bad, allow_deletions=False)
    assert chips.module.munch(4) == 17


def test_change_decorator(chips):
    assert chips.module.munch(4) == 6
    chips.main.merge(chips.cf.newdeco, allow_deletions=False)
    assert chips.module.munch(4) == 8


def test_change_decorator_multiple(chips):
    assert chips.module.munch(4) == 6
    chips.main.merge(chips.cf.newdeco, allow_deletions=False)
    assert chips.module.munch(4) == 8
    chips.main.merge(chips.cf.newdeco2, allow_deletions=False)
    assert chips.module.munch(4) == 10


def test_change_decorator_then_fn(chips):
    assert chips.module.munch(4) == 6
    chips.main.merge(chips.cf.newdeco, allow_deletions=False)
    chips.main.merge(chips.cf.newfn, allow_deletions=False)
    assert chips.module.munch(4) == 404


def test_change_fn_then_decorator(chips):
    assert chips.module.munch(4) == 6
    chips.main.merge(chips.cf.newfn, allow_deletions=False)
    chips.main.merge(chips.cf.newdeco, allow_deletions=False)
    assert chips.module.munch(4) == 404


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
    dandelion.main.merge(dandelion.cf.repl, allow_deletions=False)
    assert dandelion.read() == orig
    dandelion.main.commit()
    assert dandelion.read() == dandelion.read("outcome")


def test_commit_partial_2(dandelion):
    orig = dandelion.read()
    (plack_code,) = [
        x
        for x in dandelion.main.root.walk()
        if x.get_object() is dandelion.module.plack.__code__
    ]
    dandelion.main.merge(
        dandelion.cf.repl,
        allow_deletions=[plack_code],
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
    assert firmament.read().strip() == firmament.read("result").strip()


def test_change_supermethod(glamour):
    assert glamour.module.Scarf(5).swagger() == 10
    glamour.main.merge(glamour.cf.mod, allow_deletions=False)
    assert glamour.module.Scarf(5).swagger() == 15


def test_remove_super(glamour):
    assert glamour.module.Scarf(5).swagger() == 10
    glamour.main.merge(glamour.cf.mod2)
    assert glamour.module.Scarf(5).swagger() == 1234


def test_add_class_statement(glamour):
    assert glamour.module.Scarf(5).swagger() == 10
    glamour.main.merge(glamour.cf.mod3)
    assert glamour.module.Scarf(5).swagger() == 50
    assert glamour.module.Scarf(5).also_swagger() == 50
    assert glamour.module.Scarf(5).hello() == "hello!"


def test_bad_statement(iguana):
    # This tests that one bad statement will not interfere with the rest of the
    # changes.
    assert iguana.module.lizard(3) == "sss"
    iguana.main.merge(iguana.cf.bad)
    assert iguana.module.lizard(3) == "ssssss"


def test_associate(ballon):
    glb = {"a": 2}
    ballon.main.associate(glb)
    assert ballon.main.root.get_globals() is glb

    with pytest.raises(TypeError):
        ballon.main.associate(1234)


def test_custom_conform(jackfruit):
    assert jackfruit.module.jack1(3, 4) == 12
    assert jackfruit.module.jack2(3, 4) == 12

    assert jackfruit.module.jack1.__code__.co_name == "jack1"
    assert jackfruit.module.jack2.__code__.co_name == "jack2"

    jackfruit.main.merge(jackfruit.cf.mod)

    assert jackfruit.module.jack1(3, 4) == 7
    assert jackfruit.module.jack2(3, 4) == 7

    assert jackfruit.module.jack1.__code__.co_name == "jack1"
    assert jackfruit.module.jack2.__code__.co_name == "jack2"

    # Trigger a special path in collect_all
    codereg.collect_all()
    assert len(codereg.functions[jackfruit.module.jack1.__code__]) == 2


def test_ignore_future_flags_fails(kilroy):
    """when we don't respect __future__.annotations, we can't compile the new function"""
    with pytest.raises(AttributeError):
        _ = kilroy.module.f

    # disable respecting future flags:
    with patch("jurigged.codetools._get_future_compiler_flags", side_effect=0):
        kilroy.main.merge(kilroy.cf.new)

        with pytest.raises(AttributeError):
            _ = kilroy.module.f


def test_respect_future_flags_succeeds(kilroy):
    """when we do respect future flags, it works!"""
    with pytest.raises(AttributeError):
        _ = kilroy.module.f

    kilroy.main.merge(kilroy.cf.new)
    assert "jeb" == kilroy.module.f("jeb")


def test_future_flag_name_collisions_dont_cause_issues(kilroy):
    with pytest.raises(AttributeError):
        _ = kilroy.module.f

    kilroy.main.merge(kilroy.cf.name_collision)
    assert "tuse" == kilroy.module.f("tuse")
