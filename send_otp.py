import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

# Configuration - Load sensitive data from .env file
load_dotenv()

# Gmail SMTP Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Use environment variables or hard-coded values (for testing)
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS', 'nserekonajib3@gmail.com')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', 'obfp pczm iemq atlz')
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://qflnvnabxlzrwjwrnnhq.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFmbG52bmFieGx6cndqd3JubmhxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NjA1OTEwMCwiZXhwIjoyMDgxNjM1MTAwfQ.KDJUwitk1PpELsjnvR-e3UIuflp0WU8qg-KrtAeokyc')

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def generate_otp(length=6):
    """Generate a numeric OTP of specified length."""
    return ''.join(random.choices(string.digits, k=length))

def send_otp_email(to_email: str, otp_code: str, user_name: str = "User"):
    """
    Sends an OTP code to the user's email.
    """
    subject = "Your OTP Code for LUNSERK SACCO"
    
    # Create a simple HTML email body
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                line-height: 1.6; 
                color: #333; 
                max-width: 600px; 
                margin: 0 auto; 
                padding: 20px; 
                background-color: #f5f5f5;
            }}
            .container {{ 
                background: white; 
                border-radius: 10px; 
                overflow: hidden; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .header {{ 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 30px; 
                text-align: center; 
                color: white; 
            }}
            .content {{ 
                padding: 30px; 
            }}
            .otp-code {{ 
                font-size: 32px; 
                letter-spacing: 10px; 
                font-weight: bold; 
                color: #667eea; 
                text-align: center; 
                padding: 20px; 
                background: #f7f7f7; 
                border-radius: 8px; 
                margin: 20px 0; 
                border: 2px dashed #667eea;
            }}
            .footer {{ 
                margin-top: 30px; 
                padding-top: 20px; 
                border-top: 1px solid #eee; 
                color: #777; 
                font-size: 0.9em; 
                text-align: center;
            }}
            .warning {{ 
                background: #fff3cd; 
                border-left: 4px solid #ffc107; 
                padding: 10px; 
                margin: 20px 0; 
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin: 0; font-size: 24px;">LUNSERK TECHNOLOGIES</h1>
                <p style="margin: 5px 0 0 0; font-size: 16px; opacity: 0.9;">SACCO Management System</p>
            </div>
            <div class="content">
                <h2 style="color: #333; margin-top: 0;">Hello {user_name},</h2>
                <p>Please use the following One-Time Password (OTP) to complete your authentication:</p>
                
                <div class="otp-code">{otp_code}</div>
                
                <div class="warning">
                    <strong>⚠️ Security Notice:</strong> This OTP is valid for 10 minutes only.
                    Do not share this code with anyone.
                </div>
                
                <p>If you didn't request this OTP, please ignore this email or contact our support team immediately.</p>
                
                <div class="footer">
                    <p><strong>Tagline:</strong> Foundation For Your Digital Transformation</p>
                    <p>This is an automated message, please do not reply.</p>
                    <p style="font-size: 0.8em; color: #999;">
                        &copy; 2024 LUNSERK TECHNOLOGIES. All rights reserved.
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    # Setup the MIME
    msg = MIMEMultipart('alternative')
    msg['From'] = f"LUNSERK SACCO <{EMAIL_ADDRESS}>"
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    try:
        # Connect to server and send email
        print(f"Attempting to send email to: {to_email}")
        print(f"Using SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
        print(f"From email: {EMAIL_ADDRESS}")
        
        # Debug: Check if credentials are set
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
            print("ERROR: Email credentials are not set properly!")
            return False
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()  # Can be omitted
            server.starttls()  # Secure the connection
            server.ehlo()  # Can be omitted
            
            print("Attempting login...")
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            print("Login successful!")
            
            server.send_message(msg)
            print(f"✓ OTP email sent successfully to {to_email}")
            return True
            
    except smtplib.SMTPAuthenticationError as e:
        print(f"✗ SMTP Authentication Error: {e}")
        print("Please check your email credentials and ensure:")
        print("1. You're using the correct email and password")
        print("2. You've enabled 'Less Secure Apps' or created an 'App Password'")
        print("3. For Gmail, you might need to enable 2FA and create an app-specific password")
        return False
        
    except Exception as e:
        print(f"✗ Failed to send email to {to_email}. Error: {e}")
        return False

def save_otp_to_db(user_id: str, otp_code: str):
    """
    Saves or updates the OTP code and its expiry time for a user in the database.
    FIXED: Changed from "users" table to "admins" table
    """
    try:
        otp_expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()  # OTP valid for 10 min

        response = supabase.table("admins") \
            .update({
                "otp_code": otp_code, 
                "otp_expires_at": otp_expires_at
            }) \
            .eq("id", user_id) \
            .execute()

        if response.data:
            print(f"✓ OTP saved for admin {user_id}")
            return True
        else:
            print("✗ Failed to save OTP to database - no data returned")
            return False
    except Exception as e:
        print(f"✗ Database error while saving OTP: {e}")
        return False

def send_password_reset_email(to_email: str, reset_link: str, user_name: str = "User"):
    """
    Sends a password reset email.
    """
    subject = "Password Reset Request - LUNSERK SACCO"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                line-height: 1.6; 
                color: #333; 
                max-width: 600px; 
                margin: 0 auto; 
                padding: 20px; 
                background-color: #f5f5f5;
            }}
            .container {{ 
                background: white; 
                border-radius: 10px; 
                overflow: hidden; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .header {{ 
                background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); 
                padding: 30px; 
                text-align: center; 
                color: white; 
            }}
            .content {{ 
                padding: 30px; 
            }}
            .reset-button {{ 
                display: inline-block; 
                background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); 
                color: white; 
                padding: 12px 24px; 
                text-decoration: none; 
                border-radius: 6px; 
                font-weight: bold; 
                margin: 20px 0; 
            }}
            .footer {{ 
                margin-top: 30px; 
                padding-top: 20px; 
                border-top: 1px solid #eee; 
                color: #777; 
                font-size: 0.9em; 
                text-align: center;
            }}
            .warning {{ 
                background: #fff3cd; 
                border-left: 4px solid #ffc107; 
                padding: 10px; 
                margin: 20px 0; 
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin: 0; font-size: 24px;">LUNSERK TECHNOLOGIES</h1>
                <p style="margin: 5px 0 0 0; font-size: 16px; opacity: 0.9;">SACCO Management System</p>
            </div>
            <div class="content">
                <h2 style="color: #333; margin-top: 0;">Hello {user_name},</h2>
                <p>We received a request to reset your password for your LUNSERK SACCO admin account.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_link}" class="reset-button">Reset Your Password</a>
                </div>
                
                <p>Or copy and paste this link into your browser:</p>
                <p style="background: #f7f7f7; padding: 10px; border-radius: 4px; word-break: break-all;">
                    {reset_link}
                </p>
                
                <div class="warning">
                    <strong>⚠️ Security Notice:</strong> This link will expire in 1 hour.
                    If you didn't request this password reset, please ignore this email.
                </div>
                
                <div class="footer">
                    <p><strong>Tagline:</strong> Foundation For Your Digital Transformation</p>
                    <p>This is an automated message, please do not reply.</p>
                    <p style="font-size: 0.8em; color: #999;">
                        &copy; 2024 LUNSERK TECHNOLOGIES. All rights reserved.
                    </p>
                </div>
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
            print(f"✓ Password reset email sent to {to_email}")
            return True
    except Exception as e:
        print(f"✗ Failed to send password reset email: {e}")
        return False

# Test function
def test_email_function():
    """Test the email functionality"""
    print("Testing email functionality...")
    print(f"Email: {EMAIL_ADDRESS}")
    print(f"Supabase URL: {SUPABASE_URL}")
    
    # Test OTP generation
    otp = generate_otp()
    print(f"Generated OTP: {otp}")
    
    # Test email sending
    test_result = send_otp_email("nclenza@gmail.com", otp, "Test User")
    print(f"Email test result: {'Success' if test_result else 'Failed'}")
    
    return test_result

if __name__ == "__main__":
    test_email_function()