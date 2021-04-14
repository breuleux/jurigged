
def crunch(fn):
    def deco(*args):
        return fn(*args) + 3
    return deco
