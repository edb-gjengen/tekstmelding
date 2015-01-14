import string
import random


def generate_activation_code(length=5):
    chars = string.ascii_lowercase + string.digits
    # remove easily misinterpreted chars
    chars = chars.translate(None, '0oil1wv')
    return ''.join(random.choice(chars) for _ in range(length))
