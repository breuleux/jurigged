import re
import textwrap

import pytest

from jurigged.recode import OutOfSyncException, Recoder, make_recoder
from jurigged.register import registry

from .test_codetools import CodeCollection, ballon, tmod  # noqa


@pytest.fixture
def hyperspace(tmod):
    return CodeCollection(tmod, "hyperspace")


def test_recoder(hyperspace):
    rec = Recoder(name="test", codefile=hyperspace.main)
    assert hyperspace.module.boost() == 2
    rec.patch(
        textwrap.dedent(
            """
            def boost():
                return 200
            """
        )
    )
    assert hyperspace.module.boost() == 200
    rec.commit()

    after = open(hyperspace.main.filename).read()
    expected = open(hyperspace.cf.recoded.filename).read()
    assert after == expected


def test_recoder_2(ballon):
    initial = open(ballon.main.filename).read()

    rec = Recoder(name="test", codefile=ballon.main)
    assert ballon.module.inflate(4) == 8
    rec.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 10
            """
        )
    )
    assert ballon.module.inflate(4) == 40
    rec.revert()
    assert ballon.module.inflate(4) == 8
    rec.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 10
            """
        )
    )
    assert ballon.module.inflate(4) == 40

    assert not hasattr(ballon.module, "pop")
    rec.patch(
        textwrap.dedent(
            """
            def pop():
                return 0
            """
        )
    )
    assert ballon.module.pop() == 0

    before = open(ballon.main.filename).read()
    assert before == initial

    rec.commit()

    after = open(ballon.main.filename).read()
    expected = open(ballon.cf.recoded.filename).read()
    assert after == expected


def test_module_recoder(ballon):
    rec = make_recoder(ballon.module)
    assert ballon.module.inflate(4) == 8
    rec.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 10
            """
        )
    )
    assert ballon.module.inflate(4) == 40


def test_function_recoder(ballon):
    rec = make_recoder(ballon.module.inflate)
    assert ballon.module.inflate(4) == 8
    rec.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 10
            """
        )
    )
    assert ballon.module.inflate(4) == 40

    with pytest.raises(ValueError):
        rec.patch(
            textwrap.dedent(
                """
                def infloote(x):
                    return x * 10
                """
            )
        )

    rec.patch_module(
        textwrap.dedent(
            """
            x = 10
            def infloote(x):
                return x * 100
            """
        )
    )
    assert ballon.module.infloote(4) == 400
    assert ballon.module.x == 10


def test_code_recoder(ballon):
    rec1 = make_recoder(ballon.module.inflate.__code__)
    rec2 = make_recoder(ballon.module.inflate)
    assert rec1.codefile is rec2.codefile
    assert rec1.focus is rec2.focus
    assert re.match(r"ballon:main__[0-9]+\.inflate", rec1.name)
    assert rec1.name == rec2.name


def test_function_recoder_delete(ballon):
    rec = make_recoder(ballon.module.inflate, deletable=True)
    assert ballon.module.inflate(4) == 8
    rec.patch("")
    assert not hasattr(ballon.module, "inflate")

    # Reinsert
    rec.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 10
            """
        )
    )
    assert ballon.module.inflate(4) == 40


def test_class_recoder(ballon):
    rec = make_recoder(ballon.module.FlatCircle)
    assert ballon.module.FlatCircle(10).volume() == -1
    rec.patch(
        textwrap.dedent(
            """
            class FlatCircle:
                def __init__(self, radius):
                    self.radius = radius

                def circumference(self):
                    return 2 * math.pi * self.radius

                def volume(self):
                    return self.radius
            """
        )
    )
    assert ballon.module.FlatCircle(10).volume() == 10


def test_method_recoder(ballon):
    rec = make_recoder(ballon.module.FlatCircle.volume)
    assert ballon.module.FlatCircle(10).volume() == -1
    rec.patch(
        textwrap.dedent(
            """
            def volume(self):
                return self.radius
            """
        )
    )
    assert ballon.module.FlatCircle(10).volume() == 10


def test_recoder_registry(ballon):
    rec = make_recoder(ballon.module.inflate)
    assert ballon.module.inflate(4) == 8
    rec.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 10
            """
        )
    )
    cf, defn = registry.find(ballon.module.inflate)
    assert cf is rec.codefile
    assert cf.filename == ballon.main.filename


def test_recoder_patch_registry(ballon):
    rec = make_recoder(ballon.module.inflate)
    assert ballon.module.inflate(4) == 8
    rec.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 10
            """
        )
    )

    # ballon.module.inflate.__code__.co_filename has changed, so this could
    # behave badly
    rec2 = make_recoder(ballon.module.inflate)
    assert rec.codefile is rec2.codefile
    assert rec.focus is rec2.focus

    # Test with __code__ directly
    rec2 = make_recoder(ballon.module.inflate.__code__)
    assert rec.codefile is rec2.codefile
    assert rec.focus is rec2.focus


def test_recoder_out_of_sync(ballon):
    rec1 = make_recoder(ballon.module.inflate)
    rec2 = make_recoder(ballon.module.inflate)
    assert ballon.module.inflate(4) == 8
    rec1.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 10
            """
        )
    )
    assert ballon.module.inflate(4) == 40

    rec2.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 20
            """
        )
    )
    assert ballon.module.inflate(4) == 80

    rec2.commit()
    with pytest.raises(OutOfSyncException):
        rec1.commit()

    assert ballon.module.inflate(4) == 80
    rec1.repatch()
    assert ballon.module.inflate(4) == 40
    rec1.commit()


def test_recoder_out_of_sync_2(ballon):
    rec1 = make_recoder(ballon.module.inflate)
    rec2 = make_recoder(ballon.module.inflate)
    assert ballon.module.inflate(4) == 8
    # Patch to what it was before
    rec1.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 2
            """
        )
    )

    rec2.patch(
        textwrap.dedent(
            """
            def inflate(x):
                return x * 20
            """
        )
    )
    assert ballon.module.inflate(4) == 80

    rec2.commit()
    with pytest.raises(OutOfSyncException):
        rec1.commit()

    assert ballon.module.inflate(4) == 80
    rec1.repatch()
    assert ballon.module.inflate(4) == 8
    rec1.commit()
