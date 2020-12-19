import math


class Sphere:
    def __init__(self, radius):
        self.radius = radius

    def volume(self):
        return 4 / 3 * math.pi * self.radius ** 3


def inflate(x):
    return x * 3


class FlatCircle:
    def __init__(self, radius):
        self.radius = radius

    def circumference(self):
        return 2 * math.pi * self.radius

    def volume(self):
        return 0


def deflate(x):
    return x / 3
