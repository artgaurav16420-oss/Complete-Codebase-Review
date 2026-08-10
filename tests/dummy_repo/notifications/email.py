from auth.user import get_user_profiles

def send_email(to, subject, body):
    print(f"Sending to {to}: {subject}")

def notify_admins(event):
    admins = ["admin@example.com"]
    profiles = get_user_profiles(admins)
    for admin in admins:
        profile = profiles.get(admin)
        if profile:
            send_email(profile["email"], f"Event: {event}", "Please review")
