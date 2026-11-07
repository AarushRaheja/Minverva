from auth.sessions import user_for


def bill_owner(token):
    user = user_for(token)
    return f"bill:{user}" if user else None
