import textwrap

import pytest

from jurigged.recode import OutOfSyncException, Recoder, make_recoder
from jurigged.register import registry

from .test_codefile import ballon, tmod  # noqa


def test_recoder(ballon):
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


def test_function_recoder_delete(ballon):
    rec = make_recoder(ballon.module.inflate, deletable=True)
    assert ballon.module.inflate(4) == 8
    rec.patch("")
    assert not hasattr(ballon.module, "inflate")


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
