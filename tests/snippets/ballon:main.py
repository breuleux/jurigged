import math


def inflate(x):
    return x * 2


class Sphere:
    def __init__(self, radius):
        self.radius = radius

    def volume(self):
        return 4 / 3 * math.pi * self.radius ** 3


class FlatCircle:
    def __init__(self, radius):
        self.radius = radius

    def unsightly(self):
        return "yuck"

    def volume(self):
        return -1


def uninteresting():
    return None
