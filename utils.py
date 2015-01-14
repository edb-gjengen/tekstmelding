from datetime import date
from flask.json import JSONEncoder
import string
import random


class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        try:
            if isinstance(obj, date):
                return obj.isoformat()
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)


def generate_activation_code(length=5):
    chars = string.ascii_lowercase + string.digits
    # remove easily misinterpreted chars
    chars = chars.translate(None, '0oil1wv')
    return ''.join(random.choice(chars) for _ in range(length))
