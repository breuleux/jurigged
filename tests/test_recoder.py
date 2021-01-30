import textwrap

from jurigged.recode import Recoder

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
