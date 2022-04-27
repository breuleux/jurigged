import pytest

from jurigged.rescript import redirect, redirect_code


def doubler(f):
    def wrap(*args, **kwargs):
        return f(*args, **kwargs) * 2

    return wrap


def test_redirect():
    def f(x):
        return x

    orig_f = f
    assert f(10) == 10
    redirect(f, doubler)
    assert f is orig_f
    assert f(10) == 20


def test_redirect_code():
    def f(x):
        return x

    orig_f = f
    assert f(10) == 10
    redirect_code(f.__code__, doubler)
    assert f is orig_f
    assert f(10) == 20


def test_redirect_code_invalid():
    def f(x):
        return x

    co = f.__code__
    del f
    with pytest.raises(Exception, match="requires exactly one function"):
        redirect_code(co, doubler)
