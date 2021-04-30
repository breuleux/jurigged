import gc
import sys
import types


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

    def setup(self):
        self.acquire_existing()
        sys.addaudithook(make_audithook(self))

    def acquire_existing(self):
        for obj in gc.get_objects():
            if isinstance(obj, types.FunctionType):
                co = obj.__code__
                self.assimilate(
                    co, (co.co_filename, *obj.__qualname__.split("."))
                )

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


db = _CodeDB()
db.setup()
