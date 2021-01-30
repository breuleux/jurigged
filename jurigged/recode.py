import linecache
from itertools import count

from .codefile import CodeFile, splitlines

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
        self.saved = False

    def commit(self):
        self.codefile.commit()
        self.saved = True
