import linecache
from itertools import count
from types import FunctionType, ModuleType

from ovld import ovld

from .codefile import CodeFile, splitlines
from .register import registry

_count = count(1)


def virtual_file(name, contents):
    filename = f"<{name}#{next(_count)}>"
    linecache.cache[filename] = (None, None, splitlines(contents), filename)
    return filename


class Recoder:
    def __init__(self, name, codefile):
        self.name = name
        self.codefile = codefile

    def patch(self, new_code):
        filename = virtual_file(self.name, new_code)
        cf = CodeFile(filename=filename, source=new_code)
        registry.cache[filename] = self.codefile
        self.codefile.merge(cf, deletable=False)
        self.source = new_code

    def commit(self):
        self.codefile.commit()

    def revert(self):
        self.codefile.refresh()


@ovld
def make_recoder(module: ModuleType):
    cf = registry.find(module)
    return cf and Recoder(name=module.__name__, codefile=cf)


@ovld
def make_recoder(obj: (FunctionType, type)):
    cf, defn = registry.find(obj)
    name = f"{obj.__module__}.{obj.__qualname__}"
    return cf and Recoder(name=name, codefile=cf)
