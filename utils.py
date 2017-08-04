from datetime import datetime
from flask.json import JSONEncoder
from flask import current_app, request, abort, g
from functools import wraps


class MyJSONEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return super(MyJSONEncoder, self).default(o)


def require_token(func):
    @wraps(func)
    def check_token(*args, **kwargs):
        if 'Authorization' not in request.headers:
            abort(401)
        auth_type, token = request.headers.get('Authorization').split(' ')
        if auth_type != 'Token':
            abort(401)
        users = current_app.config.get('API_KEYS', {})
        if token not in users.keys():
            abort(401)
        g.user = users.get(token)
        return func(*args, **kwargs)
    return check_token
