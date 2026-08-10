import unittest
from unittest.mock import patch

class TestEmail(unittest.TestCase):
    @patch('builtins.print')
    def test_send_email(self, mock_print):
        # We need to import locally to avoid circular import issues at module level
        # if other tests or code load this module.
        from notifications.email import send_email
        send_email("test@example.com", "Test Subject", "Test Body")
        mock_print.assert_called_once_with("Sending to test@example.com: Test Subject")

    @patch('notifications.email.send_email')
    @patch('auth.user.get_user_profile')
    def test_notify_admins(self, mock_get_user_profile, mock_send_email):
        from notifications.email import notify_admins
        # Setup mock behavior
        mock_get_user_profile.return_value = {"email": "admin@example.com"}

        # Call the function
        notify_admins("System Update")

        # Verify get_user_profile was called with the correct admin
        mock_get_user_profile.assert_called_once_with("admin@example.com")

        # Verify send_email was called with the correct arguments
        mock_send_email.assert_called_once_with("admin@example.com", "Event: System Update", "Please review")

if __name__ == "__main__":
    unittest.main()
