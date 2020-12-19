
def crunch(fn):
    def deco(*args):
        return fn(*args) + 1
    return deco
