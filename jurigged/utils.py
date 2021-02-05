import fnmatch
import os


class EventSource(list):
    def __init__(self, *, save_history=False):
        if save_history:
            self._history = []
        else:
            self._history = None

    def register(self, listener, apply_history=True):
        if self._history and apply_history:
            for args, kwargs in self._history:
                listener(*args, **kwargs)
        self.append(listener)
        return listener

    def emit(self, *args, **kwargs):
        for listener in self:
            listener(*args, **kwargs)
        if self._history is not None:
            self._history.append((args, kwargs))


class IDSet:
    def __init__(self):
        self._data = {}

    def add(self, x):
        self._data[id(x)] = x

    def remove(self, x):
        del self._data[id(x)]

    def __iter__(self):
        return iter(self._data.values())


def glob_filter(pattern):
    if pattern.startswith("~"):
        pattern = os.path.expanduser(pattern)
    elif not pattern.startswith("/"):
        pattern = os.path.abspath(pattern)

    if os.path.isdir(pattern):
        pattern = os.path.join(pattern, "*")

    def matcher(filename):
        return fnmatch.fnmatch(filename, pattern)

    return matcher
