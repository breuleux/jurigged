
from collections import defaultdict
from .utils import IDSet
import gc
import sys
import types


class _CodeDB:
    def __init__(self):
        self.codes = {}

    def setup(self):
        self.acquire_existing()
        sys.addaudithook(self.audithook)

    def acquire_existing(self):
        for obj in gc.get_objects():
            if isinstance(obj, types.FunctionType):
                co = obj.__code__
                self.assimilate(co, (co.co_filename, *obj.__qualname__.split(".")))

    def audithook(self, event, obj):
        # Note: Python does not trace audit hooks, so normal use will not show
        # coverage of this function even if it is executed
        if event == "exec":
            code, = obj
            self.assimilate(code)

    def assimilate(self, code, path=()):
        if code.co_name == "<module>":
            name = code.co_filename
        elif code.co_name.startswith("<"):
            return
        else:
            name = code.co_name
        if name:
            path = (*path, name)
            self.codes[path] = code
        for ct in code.co_consts:
            if isinstance(ct, types.CodeType):
                self.assimilate(ct, path)


db = _CodeDB()
db.setup()
