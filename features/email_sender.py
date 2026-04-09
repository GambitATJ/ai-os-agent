import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from db_manager import SQLiteManager

def send_email(to_name: str, subject: str, 
               body: str, attachment_path: str = None) -> bool:
    """
    Sends an email using stored Gmail credentials.
    Resolves to_name to email via contacts table.
    Returns True on success, False on failure.
    """
    db = SQLiteManager()
    
    sender_email = db.get_profile("email")
    app_password = db.get_profile("gmail_app_password")
    sender_name = db.get_profile("name") or "User"
    
    if not sender_email or not app_password:
        print("  ✗  Email not configured. Run: "
              "python -m cli.main setup-profile")
        return False
    
    # Resolve recipient
    recipient_email = db.get_contact(to_name)
    if not recipient_email:
        # Check if to_name looks like an email address
        if "@" in to_name:
            recipient_email = to_name
        else:
            print(f"  ✗  Contact '{to_name}' not found.")
            print(f"     Add them with: "
                  f"python -m cli.main setup-profile")
            return False
    
    print(f"\n  📧  Sending email to {to_name} "
          f"<{recipient_email}>")
    
    msg = MIMEMultipart()
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    
    if attachment_path:
        attachment_path = os.path.expanduser(attachment_path)
        if os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = os.path.basename(attachment_path)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={filename}"
            )
            msg.attach(part)
            print(f"  📎  Attached: {filename}")
        else:
            print(f"  ⚠  Attachment not found: "
                  f"{attachment_path}")
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)
        print(f"  ✓  Email sent to {recipient_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("  ✗  Gmail authentication failed.")
        print("     Check your app password at: "
              "myaccount.google.com/apppasswords")
        return False
    except Exception as e:
        print(f"  ✗  Email failed: {e}")
        return False
