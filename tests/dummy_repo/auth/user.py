def create_user(name, email):
    from notifications.email import send_email
    user_id = hash(name)
    send_email(email, "Welcome", f"Hi {name}")
    return user_id

def get_user_profile(user_id):
    return {"id": user_id, "name": "test", "email": "test@example.com"}

def get_user_profiles(user_ids):
    # Simulates a batch DB query
    return {uid: {"id": uid, "name": "test", "email": "test@example.com"} for uid in user_ids}
