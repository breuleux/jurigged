
class Rememberer:
    def __init__(self):
        self.funcs = []

    def register(self, fn):
        self.funcs.append(fn)
        fn.__conform__ = lambda new: self.recode(fn, new)
        return self

    def recode(self, fn, new):
        if new is None:
            self.funcs.remove(fn)
        else:
            fn.__code__ = new.__code__

    def __call__(self, *args):
        return [fn(*args) for fn in self.funcs]


activities = Rememberer()


@activities.register
def do(x):
    return f"Paint {x} canvasses"


@activities.register
def do(x):
    return f"Sing {x} songs"


@activities.register
def do(x):
    return f"Dance for {x} hours"
