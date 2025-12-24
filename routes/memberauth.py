# memberauth.py
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
from datetime import datetime, timezone, timedelta
import uuid
import json
from decimal import Decimal
from dotenv import load_dotenv
import random
import string
from postgrest.exceptions import APIError

# Import the send_otp functionality
from sendotp import send_otp_email

load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Create Blueprint
memberauth_bp = Blueprint('memberauth', __name__, url_prefix='/member')

# Helper functions
def get_current_utc_time():
    """Get current UTC time with timezone awareness."""
    return datetime.now(timezone.utc)

def generate_otp(length=6):
    """Generate a numeric OTP of specified length."""
    return ''.join(random.choices(string.digits, k=length))

# Member login required decorator
def member_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'member_logged_in' not in session or not session.get('member_logged_in'):
            flash('Please login to access this page', 'error')
            return redirect(url_for('memberauth.member_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_member_by_email(email):
    """Safely get member by email without using .single()"""
    try:
        response = supabase.table('members')\
            .select('id, email, full_name, account_status, member_number')\
            .eq('email', email)\
            .execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]  # Return first match
        return None
        
    except APIError as e:
        # This handles the PGRST116 error gracefully
        if 'PGRST116' in str(e):
            return None
        raise e
    except Exception as e:
        print(f"Error fetching member: {e}")
        return None

def get_member_by_id(member_id):
    """Safely get member by ID"""
    try:
        response = supabase.table('members')\
            .select('*')\
            .eq('id', member_id)\
            .execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
        
    except Exception as e:
        print(f"Error fetching member by ID: {e}")
        return None

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

        # Fetch member safely
        member = get_member_by_email(email)
        
        if not member:
            # Don't reveal if email exists or not (security best practice)
            flash('If your email exists in our system, you will receive an OTP.', 'info')
            return render_template('member/login.html')

        # Check ACTIVE status
        if member.get('account_status') != 'active':
            flash('Your membership is inactive. Please contact admin for assistance.', 'error')
            return render_template('member/login.html')

        # Generate OTP
        otp = generate_otp()
        otp_hash = generate_password_hash(otp)
        expires_at = (get_current_utc_time() + timedelta(minutes=10)).isoformat()

        # Save OTP
        try:
            supabase.table('member_otps').insert({
                'member_id': member['id'],
                'otp_hash': otp_hash,
                'expires_at': expires_at,
                'used': False
            }).execute()
        except Exception as e:
            flash('Failed to generate OTP. Please try again.', 'error')
            print(f"OTP save error: {e}")
            return render_template('member/login.html')

        # Send OTP using the imported function
        try:
            send_otp_email(member['email'], otp, member['full_name'])
        except Exception as e:
            print(f"Email sending error: {e}")
            # Don't fail login if email fails, just log it

        # Store temp session
        session['otp_member_id'] = member['id']
        session['otp_attempts'] = 0  # Track OTP attempts

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
        # Increment attempt counter
        session['otp_attempts'] = session.get('otp_attempts', 0) + 1
        
        # Limit attempts
        if session.get('otp_attempts', 0) > 5:
            session.pop('otp_member_id', None)
            session.pop('otp_attempts', None)
            flash('Too many OTP attempts. Please login again.', 'error')
            return redirect(url_for('memberauth.member_login'))

        otp_input = request.form.get('otp', '').strip()

        if not otp_input or len(otp_input) != 6:
            flash('Please enter a valid 6-digit OTP', 'error')
            return render_template('member/verify_otp.html')

        current_time = get_current_utc_time()
        
        # Fetch latest valid OTP
        try:
            otp_res = supabase.table('member_otps')\
                .select('*')\
                .eq('member_id', member_id)\
                .eq('used', False)\
                .gt('expires_at', current_time.isoformat())\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
                
            if not otp_res.data:
                flash('Invalid or expired OTP. Please request a new one.', 'error')
                return render_template('member/verify_otp.html')
                
            otp_row = otp_res.data[0]
            
        except Exception as e:
            flash('Error verifying OTP. Please try again.', 'error')
            print(f"OTP fetch error: {e}")
            return render_template('member/verify_otp.html')

        # Verify OTP
        if not check_password_hash(otp_row['otp_hash'], otp_input):
            remaining_attempts = 5 - session.get('otp_attempts', 0)
            flash(f'Incorrect OTP. {remaining_attempts} attempts remaining.', 'error')
            return render_template('member/verify_otp.html')

        # Mark OTP as used
        try:
            supabase.table('member_otps')\
                .update({'used': True})\
                .eq('id', otp_row['id'])\
                .execute()
        except Exception as e:
            print(f"OTP update error: {e}")

        # Fetch member
        member = get_member_by_id(member_id)
        
        if not member:
            flash('Error fetching member details. Please login again.', 'error')
            return redirect(url_for('memberauth.member_login'))

        # Final safety check
        if member.get('account_status') != 'active':
            flash('Account inactive. Please contact admin for assistance.', 'error')
            return redirect(url_for('memberauth.member_login'))

        # Create login session
        session.clear()
        session['member_logged_in'] = True
        session['member_id'] = member['id']
        session['member_email'] = member['email']
        session['member_name'] = member['full_name']
        session['member_number'] = member.get('member_number', '')
        session['last_login'] = get_current_utc_time().isoformat()

        # Update login timestamp
        try:
            supabase.table('members')\
                .update({'last_login': get_current_utc_time().isoformat()})\
                .eq('id', member['id'])\
                .execute()
        except Exception as e:
            print(f"Login timestamp update error: {e}")

        flash(f'Welcome {member["full_name"]}', 'success')
        return redirect(url_for('member.dashboard'))

    return render_template('member/verify_otp.html')

@memberauth_bp.route('/logout')
def member_logout():
    """Logout member"""
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('memberauth.member_login'))

# Forgot Password Route
@memberauth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle password reset request"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email is required', 'error')
            return render_template('member/forgot_password.html')
        
        # Check if member exists
        member = get_member_by_email(email)
        
        # Always show success message for security (don't reveal if email exists)
        flash('If your email exists in our system, you will receive password reset instructions.', 'info')
        
        if not member:
            return render_template('member/forgot_password.html')
        
        # Generate reset token
        reset_token = str(uuid.uuid4())
        expires_at = (get_current_utc_time() + timedelta(hours=1)).isoformat()
        
        try:
            # Save reset token
            supabase.table('password_resets').insert({
                'member_id': member['id'],
                'reset_token': reset_token,
                'expires_at': expires_at,
                'used': False
            }).execute()
            
            # You could also create a separate function for sending password reset emails
            # For now, we can use the same send_otp_email or create a new function in sendotp.py
            # send_password_reset_email(member['email'], reset_token, member['full_name'])
            
        except Exception as e:
            print(f"Reset token error: {e}")
        
        return render_template('member/forgot_password.html')
    
    return render_template('member/forgot_password.html')

# Health check endpoint
@memberauth_bp.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Test database connection without .single()
        response = supabase.table('members').select('id').limit(1).execute()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': get_current_utc_time().isoformat(),
            'database': 'connected',
            'service': 'member_auth'
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': get_current_utc_time().isoformat(),
            'service': 'member_auth'
        }), 500