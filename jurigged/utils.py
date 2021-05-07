import fnmatch
import os
import types

from ovld import ovld

from .codedb import db

###########
# Conform #
###########


class ConformException(Exception):
    pass


@ovld.dispatch
def conform(self, obj1, obj2, **kwargs):
    if hasattr(obj1, "__conform__"):
        obj1.__conform__(obj2)
    else:
        self.resolve(obj1, obj2)(obj1, obj2, **kwargs)


@ovld
def conform(self, obj1: types.FunctionType, obj2: types.FunctionType, **kwargs):
    self(obj1, obj2.__code__, **kwargs)
    obj1.__defaults__ = obj2.__defaults__
    obj1.__kwdefaults__ = obj2.__kwdefaults__


@ovld
def conform(self, obj1: types.FunctionType, obj2: types.CodeType, **kwargs):
    fv1 = obj1.__code__.co_freevars
    fv2 = obj2.co_freevars
    if fv1 != fv2:
        msg = (
            f"Cannot replace closure `{obj1.__name__}` because the free "
            f"variables changed. Before: {fv1}; after: {fv2}."
        )
        if ("__class__" in (fv1 or ())) ^ ("__class__" in (fv2 or ())):
            msg += " Note: The use of `super` entails the `__class__` free variable."
        raise ConformException(msg)
    db.replace_code(obj1, obj2)


@ovld
def conform(
    self,
    obj1: types.CodeType,
    obj2: (types.CodeType, types.FunctionType, type(None)),
    **kwargs,
):
    for fn in db.get_functions(obj1, **kwargs):
        self(fn, obj2, **kwargs)


@ovld
def conform(self, obj1, obj2, **kwargs):
    pass


########
# Misc #
########


class EventSource(list):
    def __init__(self, *, save_history=False):
        if save_history:
            self._history = []
        else:
            self._history = None

    def register(self, listener, apply_history=True):
        if self._history and apply_history:
            for args, kwargs in self._history:
                listener(*args, **kwargs)
        self.append(listener)
        return listener

    def emit(self, *args, **kwargs):
        for listener in self:
            listener(*args, **kwargs)
        if self._history is not None:
            self._history.append((args, kwargs))


def glob_filter(pattern):
    if pattern.startswith("~"):
        pattern = os.path.expanduser(pattern)
    elif not pattern.startswith("/"):
        pattern = os.path.abspath(pattern)

    if os.path.isdir(pattern):
        pattern = os.path.join(pattern, "*")

    def matcher(filename):
        return fnmatch.fnmatch(filename, pattern)

    return matcher


def shift_lineno(co, delta):
    if isinstance(co, types.CodeType):
        return co.replace(
            co_firstlineno=co.co_firstlineno + delta,
            co_consts=tuple(shift_lineno(ct, delta) for ct in co.co_consts),
        )
    else:
        return co
