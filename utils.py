import string
import random
from datetime import datetime
from flask.json import JSONEncoder


def generate_activation_code(length=5):
    chars = string.ascii_lowercase + string.digits
    # remove easily misinterpreted chars
    chars = chars.translate(None, '0oil1wv')
    return ''.join(random.choice(chars) for _ in range(length))


class MyJSONEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return super(MyJSONEncoder, self).default(o)
