
def crunch(fn):
    def deco(*args):
        return fn(*args) + 1
    return deco


@crunch
@crunch
def munch(x):
    return x
