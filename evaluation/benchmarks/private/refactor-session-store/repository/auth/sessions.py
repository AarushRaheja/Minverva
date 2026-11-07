import secrets

_SESSIONS = {}


def create(user):
    token = secrets.token_hex(8)
    _SESSIONS[token] = user
    return token


def user_for(token):
    return _SESSIONS.get(token)


def revoke(token):
    _SESSIONS.pop(token, None)


def clear():
    _SESSIONS.clear()
