from notifications.email import send_email

def create_user(name, email):
    user_id = hash(name)
    send_email(email, "Welcome", f"Hi {name}")
    return user_id

def get_user_profile(user_id):
    return {"id": user_id, "name": "test", "email": "test@example.com"}

def get_user_profiles(user_ids):
    return {user_id: {"id": user_id, "name": "test", "email": "test@example.com"} for user_id in user_ids}
