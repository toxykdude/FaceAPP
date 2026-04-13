"""
Email notification service.

Sends emails when SMTP is configured in environment variables.
If SMTP settings are missing, emails are logged but not sent.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EmailService:
    """Email notification service with SMTP support."""
    
    def __init__(self):
        from core.config import settings
        self.smtp_host = getattr(settings, 'SMTP_HOST', None)
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_user = getattr(settings, 'SMTP_USER', None)
        self.smtp_password = getattr(settings, 'SMTP_PASSWORD', None)
        self.smtp_from = getattr(settings, 'SMTP_FROM_EMAIL', 'noreply@powerhousegym.co')
        self.enabled = bool(self.smtp_host and self.smtp_user)
    
    def _send_email(self, to: str, subject: str, body: str, html: Optional[str] = None):
        """Send an email (or log if SMTP not configured)."""
        if not self.enabled:
            logger.info(f"[EMAIL DISABLED] To: {to}, Subject: {subject}")
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_from
            msg["To"] = to
            
            msg.attach(MIMEText(body, "plain"))
            if html:
                msg.attach(MIMEText(html, "html"))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_from, to, msg.as_string())
            
            logger.info(f"Email sent to {to}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False
    
    def send_welcome_email(self, member_email: str, member_name: str):
        """Send welcome email to new member."""
        subject = "Welcome to PowerHouse Gym!"
        body = f"""
Hello {member_name},

Welcome to PowerHouse Gym! We're excited to have you as a member.

Your account has been created in our system. You can now access the gym
using our facial recognition system once you complete your enrollment.

If you have any questions, please don't hesitate to contact us.

Best regards,
PowerHouse Gym Team
        """
        self._send_email(member_email, subject, body.strip())
    
    def send_membership_expiring(self, member_email: str, member_name: str, 
                                  end_date: str, days_left: int):
        """Send membership expiring notification."""
        subject = f"Your membership expires in {days_left} days"
        body = f"""
Hello {member_name},

This is a friendly reminder that your PowerHouse Gym membership
expires on {end_date} ({days_left} days from now).

To continue enjoying our facilities, please visit us to renew your membership.

Best regards,
PowerHouse Gym Team
        """
        self._send_email(member_email, subject, body.strip())
    
    def send_membership_expired(self, member_email: str, member_name: str):
        """Send membership expired notification."""
        subject = "Your membership has expired"
        body = f"""
Hello {member_name},

Your PowerHouse Gym membership has expired.

To regain access to our facilities, please visit us to renew your membership.

Best regards,
PowerHouse Gym Team
        """
        self._send_email(member_email, subject, body.strip())


# Global instance
email_service = EmailService()
