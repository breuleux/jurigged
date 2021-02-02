import textwrap

from jurigged.recode import Recoder, function_recoder, module_recoder
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
    rec = module_recoder(ballon.module)
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
    rec = function_recoder(ballon.module.inflate)
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


def test_recoder_registry(ballon):
    rec = function_recoder(ballon.module.inflate)
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
