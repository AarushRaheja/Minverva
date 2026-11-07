import secrets


class SessionStore:
    def __init__(self):
        self._sessions = {}

    def create(self, user):
        token = secrets.token_hex(8)
        self._sessions[token] = user
        return token

    def user_for(self, token):
        return self._sessions.get(token)

    def revoke(self, token):
        self._sessions.pop(token, None)

    def clear(self):
        self._sessions.clear()
