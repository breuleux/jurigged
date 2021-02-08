def crunch(fn):
    1234
    return fn


@crunch
@crunch
@crunch
def breakfast():
    return "apples"


class Orchard:
    @staticmethod
    def mcintosh():
        return 1234

    @classmethod
    def honeycrisp(cls, a, b):
        c = a + b
        return c

    def cortland(self, x):
        y = x + 1
        z = y * y
        return self.honeycrisp(y, z)


async def juggle(a1, a2, a3):
    a4 = await a1
    a5 = await a2
    a6 = await a3
    return a4, a5, a6


def pomme():
    def ver():
        return "nyah ha ha ha"
    return ver


from functools import wraps


def arbre(fn):
    @wraps(fn)
    def branche(x, y):
        return fn(x * y)
    return branche


@arbre
def pommier(z):
    return z ** z


class FakeApple:
    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        self._color = value


out_of_place = 12
del out_of_place
