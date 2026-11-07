from auth.store import SessionStore

_DEFAULT = SessionStore()


def create(user):
    return _DEFAULT.create(user)


def user_for(token):
    return _DEFAULT.user_for(token)


def revoke(token):
    _DEFAULT.revoke(token)


def clear():
    _DEFAULT.clear()
