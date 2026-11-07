`auth/sessions.py` keeps its data in a module-level dict, so two tenants can't have separate sessions. Move the state into a `SessionStore` class in a new file, `auth/store.py`, with the methods `create(user)`, `user_for(token)`, `revoke(token)` and `clear()`. Each instance holds its own sessions.

The module-level functions in `auth/sessions.py` must keep behaving exactly as they do now, backed by one default `SessionStore` instance, and `auth/billing.py` must not need any change.

Run the visible tests with: python3 -m unittest discover -s tests/public -t tests/public
Hidden tests will also grade your work. Don't edit existing tests.
