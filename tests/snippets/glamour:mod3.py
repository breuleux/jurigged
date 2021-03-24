
def outer(self):
    return "hello!"

class Scarf(Wearable):
    def swagger(self):
        return super(Scarf, self).swagger() * 10

    also_swagger = swagger
    hello = outer
