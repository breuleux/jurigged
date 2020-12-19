
class Flower:
    def __init__(self, name):
        self.name = name

    def sing(self):
        return f"O {self.name}, how beautiful are thee!"

    def test(self):
        print("test 1 2 3")

def pluck(n):
    """New pluck.

    It's longer!
    """
    rval = n - 2
    return rval

def plack():
    return True
