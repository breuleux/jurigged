
class Wearable:
    def __init__(self, intensity):
        self.intensity = intensity

    def swagger(self):
        return self.intensity

class Scarf(Wearable):
    def swagger(self):
        return super(Scarf, self).swagger() * 2
