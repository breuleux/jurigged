class Bee:
    def __init__(self, zs):
        self.buzz = "bu" + "z" * zs
def color():
    return "yellow"
class Flower:
    def __init__(self, name, npetals):
        self.name = name
        self.npetals = npetals
    def pluck(self):
        self.npetals -= 1

    def sing(self):
        return f"O {self.name}, how beautiful are thee {self.npetals} petals!"


def pluck(n):
    """New pluck.

    It's longer!
    """
    rval = n - 2
    return rval
