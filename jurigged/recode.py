import linecache
from itertools import count

from .codefile import CodeFile, splitlines

_count = count(1)


class Recoder:
    def __init__(self, name, codefile):
        self.name = name
        self.codefile = codefile
        # self.source = ""
        # self.saved = False

    def patch(self, new_code):
        filename = f"<{self.name}#{next(_count)}>"
        linecache.cache[filename] = (None, None, splitlines(new_code), filename)
        cf = CodeFile(filename=filename, source=new_code)
        self.codefile.merge(cf, partial=True)
        self.source = new_code
        self.saved = False

    def commit(self):
        self.codefile.commit()
        self.saved = True
