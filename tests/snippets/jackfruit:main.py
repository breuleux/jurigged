import types

class Assoc:
    __slots__ = ("fn", "code")

    def __init__(self, fn, code):
        self.fn = fn
        self.code = code

    def __conform__(self, new_code):
        if new_code is not None:
            if isinstance(new_code, types.FunctionType):
                new_code = new_code.__code__
            self.fn.__code__ = new_code.replace(co_name="jack2")
            from codefind import update_cache_entry
            update_cache_entry(self, self.code, new_code)
            self.code = new_code

def jack1(x, y):
    return x * y

jack2 = types.FunctionType(
    jack1.__code__.replace(co_name="jack2"),
    globals()
)
jack2._recoder = Assoc(jack2, jack1.__code__)
