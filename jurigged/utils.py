import fnmatch
import os
import types
from dataclasses import dataclass

from ovld import ovld

##########
# Locate #
##########


@ovld
def locate(fn: types.FunctionType, catalog):
    return locate(fn.__code__, catalog)


@ovld
def locate(code: types.CodeType, catalog):
    key = (code.co_filename, code.co_firstlineno)
    return catalog.get(key, None)


@ovld
def locate(typ: type, catalog):
    key = f"{typ.__module__}.{typ.__qualname__}"
    return catalog.get(key, None)


@ovld
def locate(mod: types.ModuleType, catalog):
    return catalog.get(mod.__name__, None)


@ovld
def locate(obj: object, catalog):  # pragma: no cover
    return None


#######
# Dig #
#######


@dataclass
class Vars:
    contents: dict


@ovld.dispatch(initial_state=lambda: {"seen": set()})
def dig(self, obj, module_name):
    if id(obj) in self.seen:
        return
    elif hasattr(obj, "__functions__"):
        try:
            yield from obj.__functions__
        except Exception:  # pragma: no cover
            return
    else:
        self.seen.add(id(obj))
        yield from self.call(obj, module_name)


@ovld
def dig(self, obj: types.FunctionType, module_name):
    yield obj
    for x in obj.__closure__ or []:
        yield from self(x.cell_contents, module_name)
    if hasattr(obj, "__wrapped__"):
        yield from self(obj.__wrapped__, module_name)


@ovld
def dig(self, obj: types.ModuleType, module_name):
    yield obj
    if obj.__name__ == module_name:
        yield from dig(Vars(vars(obj)), module_name)


@ovld
def dig(self, obj: type, module_name):
    yield obj
    if obj.__module__ == module_name:
        for value in vars(obj).values():
            yield from self(value, module_name)


@ovld
def dig(self, obj: (classmethod, staticmethod), module_name):
    yield from self(obj.__func__, module_name)


@ovld
def dig(self, obj: Vars, module_name):
    for value in obj.contents.values():
        yield from self(value, module_name)


@ovld
def dig(self, obj: property, module_name):
    yield from self(obj.fget, module_name)
    yield from self(obj.fset, module_name)
    yield from self(obj.fdel, module_name)


@ovld
def dig(self, obj: object, module_name):
    yield from []


###########
# Conform #
###########


class ConformException(Exception):
    pass


@ovld.dispatch
def conform(self, obj1, obj2):
    if hasattr(obj1, "__conform__"):
        obj1.__conform__(obj2)
    else:
        self.resolve(obj1, obj2)(obj1, obj2)


@ovld
def conform(self, obj1: types.FunctionType, obj2: types.FunctionType):
    fv1 = obj1.__code__.co_freevars
    fv2 = obj2.__code__.co_freevars
    if fv1 != fv2:
        msg = (
            f"Cannot replace closure `{obj1.__name__}` because the free "
            f"variables changed. Before: {fv1}; after: {fv2}."
        )
        if ("__class__" in (fv1 or ())) ^ ("__class__" in (fv2 or ())):
            msg += " Note: The use of `super` entails the `__class__` free variable."
        raise ConformException(msg)
    obj1.__code__ = obj2.__code__
    obj1.__defaults__ = obj2.__defaults__
    obj1.__kwdefaults__ = obj2.__kwdefaults__


@ovld
def conform(self, obj1, obj2):
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


class IDSet:
    def __init__(self):
        self._data = {}

    def add(self, x):
        self._data[id(x)] = x

    def __bool__(self):
        return bool(self._data)

    def __iter__(self):
        return iter(self._data.values())


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
