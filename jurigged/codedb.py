import gc
import sys
import time
import types

from ovld import ovld

##########
# CodeDB #
##########

MAX_TIME = 0.1


def make_audithook(self):
    def watch_exec(event, obj):  # pragma: no cover
        # Note: Python does not trace audit hooks, so normal use will not show
        # coverage of this function even if it is executed
        if event == "exec":
            (code,) = obj
            self.assimilate(code)

    # The closure is faster than a method on _CodeDB
    return watch_exec


class _CodeDB:
    def __init__(self):
        self.codes = {}
        self.functions = {}
        self.last_cost = 0
        self.always_use_cache = False

    def setup(self):
        self.collect_all()
        sys.addaudithook(make_audithook(self))

    def collect_all(self):
        results = []
        for obj in gc.get_objects():
            if isinstance(obj, types.FunctionType):
                results.append((obj, obj.__code__))
            elif not hasattr(obj, "__getattr__"):
                if hasattr(obj, "__conform__"):
                    for x in gc.get_referents(obj):
                        if isinstance(x, types.CodeType):
                            results.append((obj, x))
        for obj, co in results:
            if hasattr(obj, "__qualname__"):
                self.assimilate(
                    co, (co.co_filename, *obj.__qualname__.split("."))
                )
            objects = self.functions.setdefault(co, [])
            objects.append(obj)

    def assimilate(self, code, path=()):
        if code.co_name == "<module>":  # pragma: no cover
            # Typically triggered by the audit hook
            name = code.co_filename
        elif code.co_name.startswith("<"):
            return
        else:
            name = code.co_name
        if name:
            path = (*path, name)
            self.codes[(*path, code.co_firstlineno)] = code
        for ct in code.co_consts:
            if isinstance(ct, types.CodeType):
                self.assimilate(ct, path)

    def _get_functions(self, code):
        t = time.time()
        results = [
            fn
            for fn in gc.get_referrers(code)
            if isinstance(fn, types.FunctionType) or hasattr(fn, "__conform__")
        ]
        self.functions[code] = list(results)
        self.last_cost = time.time() - t
        return results

    def get_functions(self, code, use_cache=False):
        use_cache = (
            use_cache or self.always_use_cache or self.last_cost > MAX_TIME
        )
        if use_cache and (result := self.functions.get(code, None)) is not None:
            return result
        else:
            return self._get_functions(code)

    def replace_code(self, fn, new_code):
        if (fns := self.functions.get(fn.__code__, None)) is not None:
            if fn in fns:
                fns.remove(fn)
        fn.__code__ = new_code
        fns = self.functions.setdefault(new_code, [])
        fns.append(fn)


db = _CodeDB()
db.setup()


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
