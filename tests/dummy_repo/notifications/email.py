def send_email(to, subject, body):
    print(f"Sending to {to}: {subject}")

def notify_admins(event):
    from auth.user import get_user_profile
    admins = ["admin@example.com"]
    for admin in admins:
        profile = get_user_profile(admin)
        send_email(profile["email"], f"Event: {event}", "Please review")
