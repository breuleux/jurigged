
def crunch(fn):
    def deco(*args):
        return fn(*args) + 2
    return deco
