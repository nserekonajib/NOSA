import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
from datetime import datetime, timedelta
import uuid
import json
from decimal import Decimal
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string

load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Email Configuration
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Create Blueprint
memberauth_bp = Blueprint('memberauth', __name__, url_prefix='/member')

# Helper functions
def generate_otp(length=6):
    """Generate a numeric OTP of specified length."""
    return ''.join(random.choices(string.digits, k=length))

def send_otp_email(to_email: str, otp_code: str, user_name: str = "Member"):
    """Send OTP code to member's email."""
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

def send_password_reset_email(to_email: str, reset_token: str, user_name: str = "Member"):
    """Send password reset email to member."""
    reset_link = f"{request.host_url.rstrip('/')}/member/reset-password/{reset_token}"
    subject = "Password Reset Request - LUNSERK SACCO Member Portal"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 30px; background: #f9fafb; }}
            .reset-button {{ display: inline-block; background: #2563eb; color: white; 
                            padding: 12px 24px; text-decoration: none; border-radius: 6px; 
                            font-weight: bold; margin: 20px 0; }}
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
                <p>Click the button below to reset your password:</p>
                <div style="text-align: center;">
                    <a href="{reset_link}" class="reset-button">Reset Password</a>
                </div>
                <p>Or copy this link: {reset_link}</p>
                <p>This link will expire in 1 hour.</p>
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
            print(f"Password reset email sent to {to_email}")
            return True
    except Exception as e:
        print(f"Failed to send password reset email: {e}")
        return False

# Member login required decorator
def member_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'member_logged_in' not in session or not session.get('member_logged_in'):
            flash('Please login to access this page', 'error')
            return redirect(url_for('memberauth.member_login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@memberauth_bp.route('/login', methods=['GET', 'POST'])
def member_login():
    """
    STEP 1: Member enters email → OTP sent
    """
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Email is required', 'error')
            return render_template('member/login.html')

        # Fetch member
        res = supabase.table('members')\
            .select('id, email, full_name, account_status')\
            .eq('email', email)\
            .single()\
            .execute()

        if not res.data:
            flash('Invalid email address', 'error')
            return render_template('member/login.html')

        member = res.data

        # 🔒 IMPORTANT: Check ACTIVE status
        if member['account_status'] != 'active':
            flash('Your membership is inactive. Please pay membership fee.', 'error')
            return render_template('member/login.html')

        # Generate OTP
        otp = generate_otp()
        otp_hash = generate_password_hash(otp)
        expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

        # Save OTP
        supabase.table('member_otps').insert({
            'member_id': member['id'],
            'otp_hash': otp_hash,
            'expires_at': expires_at
        }).execute()

        # Send OTP
        send_otp_email(member['email'], otp, member['full_name'])

        # Store temp session
        session['otp_member_id'] = member['id']

        flash('OTP sent to your email', 'success')
        return redirect(url_for('memberauth.verify_otp'))

    return render_template('member/login.html')



@memberauth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    """
    STEP 2: OTP verification → LOGIN
    """
    member_id = session.get('otp_member_id')

    if not member_id:
        flash('Session expired. Please login again.', 'error')
        return redirect(url_for('memberauth.member_login'))

    if request.method == 'POST':
        otp_input = request.form.get('otp')

        if not otp_input:
            flash('OTP is required', 'error')
            return render_template('member/verify_otp.html')

        # Fetch latest valid OTP
        otp_res = supabase.table('member_otps')\
            .select('*')\
            .eq('member_id', member_id)\
            .eq('used', False)\
            .gt('expires_at', datetime.utcnow().isoformat())\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()

        if not otp_res.data:
            flash('Invalid or expired OTP', 'error')
            return render_template('member/verify_otp.html')

        otp_row = otp_res.data[0]

        # Verify OTP
        if not check_password_hash(otp_row['otp_hash'], otp_input):
            flash('Incorrect OTP', 'error')
            return render_template('member/verify_otp.html')

        # Mark OTP as used
        supabase.table('member_otps')\
            .update({'used': True})\
            .eq('id', otp_row['id'])\
            .execute()

        # Fetch member
        member_res = supabase.table('members')\
            .select('*')\
            .eq('id', member_id)\
            .single()\
            .execute()

        member = member_res.data

        # 🔒 Final safety check
        if member['account_status'] != 'active':
            flash('Account inactive', 'error')
            return redirect(url_for('memberauth.member_login'))

        # ✅ LOGIN SESSION
        session.clear()
        session['member_logged_in'] = True
        session['member_id'] = member['id']
        session['member_email'] = member['email']
        session['member_name'] = member['full_name']
        session['member_number'] = member['member_number']

        # Update login timestamp
        supabase.table('members')\
            .update({'updated_at': datetime.utcnow().isoformat()})\
            .eq('id', member['id'])\
            .execute()

        print(member['id'], 'login', 'Logged in via OTP')

        flash(f'Welcome {member["full_name"]}', 'success')
        return redirect(url_for('member.dashboard'))

    return render_template('member/verify_otp.html')


@memberauth_bp.route('/logout')
def member_logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('memberauth.member_login'))

