
class Rememberer:
    def __init__(self):
        self.__functions__ = []

    def register(self, fn):
        self.__functions__.append(fn)
        fn.__conform__ = lambda new: self.recode(fn, new)
        return self

    def recode(self, fn, new):
        if new is None:
            self.__functions__.remove(fn)
        else:
            fn.__code__ = new.__code__

    def __call__(self, *args):
        return [fn(*args) for fn in self.__functions__]


activities = Rememberer()


@activities.register
def do(x):
    return f"Paint {x} canvasses"


@activities.register
def do(x):
    return f"Sing {x * 2} songs"


@activities.register
def do(x):
    return f"Dance for {x} hours"
