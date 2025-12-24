# sendotp.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# Email Configuration
EMAIL_ADDRESS = "nserekonajib3@gmail.com"
EMAIL_PASSWORD = 'obfp pczm iemq atlz'
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS', 'nserekonajib3@gmail.com')
# EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', 'obfp pczm iemq atlz')
# SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://qflnvnabxlzrwjwrnnhq.supabase.co')
# SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFmbG52bmFieGx6cndqd3JubmhxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NjA1OTEwMCwiZXhwIjoyMDgxNjM1MTAwfQ.KDJUwitk1PpELsjnvR-e3UIuflp0WU8qg-KrtAeokyc')
def send_otp_email(to_email: str, otp_code: str, user_name: str = "Member") -> bool:
    """
    Send OTP code to member's email.
    
    Args:
        to_email: Recipient email address
        otp_code: The OTP code to send
        user_name: Name of the user (optional)
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    subject = "Your OTP Code - LUNSERK SACCO Member Portal"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 30px; background: #f9fafb; }}
            .otp-code {{ font-size: 32px; letter-spacing: 10px; font-weight: bold; color: #2563eb; 
                         text-align: center; padding: 20px; background: white; border-radius: 8px; 
                         margin: 20px 0; border: 2px dashed #2563eb; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; 
                      color: #777; font-size: 0.9em; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>LUNSERK SACCO</h1>
                <p>Member Portal</p>
            </div>
            <div class="content">
                <h2>Hello {user_name},</h2>
                <p>Your OTP code for member portal access is:</p>
                <div class="otp-code">{otp_code}</div>
                <p>This OTP is valid for 10 minutes.</p>
                <p>If you didn't request this OTP, please ignore this email.</p>
            </div>
            <div class="footer">
                <p>&copy; 2024 LUNSERK SACCO. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart('alternative')
    msg['From'] = f"LUNSERK SACCO <{EMAIL_ADDRESS}>"
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
            print(f"OTP email sent to {to_email}")
            return True
    except Exception as e:
        print(f"Failed to send OTP email: {e}")
        return False