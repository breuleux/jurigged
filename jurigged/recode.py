import linecache
from itertools import count

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
        self.codefile.merge(cf, partial=True)
        self.source = new_code

    def commit(self):
        self.codefile.commit()

    def revert(self):
        self.codefile.refresh()


def module_recoder(module):
    cf = registry.find_module(module)
    return Recoder(name=module.__name__, codefile=cf)


def function_recoder(fn):
    cf, defn = registry.find_function(fn)
    name = f"{fn.__module__}.{fn.__qualname__}"
    return cf and Recoder(name=name, codefile=cf)
