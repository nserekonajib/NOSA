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
from postgrest.exceptions import APIError

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
    """Safely get member by email with password hash"""
    try:
        response = supabase.table('members')\
            .select('id, email, full_name, account_status, member_number, password_hash, default_password_used')\
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

def check_member_password(member, password):
    """Check if password is correct for member"""
    password_hash = member.get('password_hash')
    default_password_used = member.get('default_password_used', False)
    
    # If no password set yet, check against default "123"
    if not password_hash:
        if password == "123":
            return True, True  # Password correct, is default
        return False, False
    
    # If password is set, check it
    if check_password_hash(password_hash, password):
        # Check if they're using default password (should be hashed version of "123")
        if default_password_used and check_password_hash(password_hash, "123"):
            return True, True  # Password correct, is default
        return True, False  # Password correct, not default
    
    return False, False

# Routes
@memberauth_bp.route('/login', methods=['GET', 'POST'])
def member_login():
    """
    Login with email and password
    - If password is null in DB, allow login with "123"
    - If default_password_used is True, prompt for password change
    """
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required', 'error')
            return render_template('member/login.html')

        # Fetch member safely
        member = get_member_by_email(email)
        
        if not member:
            # Don't reveal if email exists or not (security best practice)
            flash('Invalid email or password', 'error')
            return render_template('member/login.html')

        # Check ACTIVE status
        if member.get('account_status') != 'active':
            flash('Your membership is inactive. Please contact admin for assistance.', 'error')
            return render_template('member/login.html')

        # Check password
        password_correct, is_default = check_member_password(member, password)
        
        if not password_correct:
            flash('Invalid email or password', 'error')
            return render_template('member/login.html')

        # Fetch full member details
        full_member = get_member_by_id(member['id'])
        if not full_member:
            flash('Error fetching member details. Please try again.', 'error')
            return render_template('member/login.html')

        # Create login session
        session.clear()
        session['member_logged_in'] = True
        session['member_id'] = member['id']
        session['member_email'] = member['email']
        session['member_name'] = member['full_name']
        session['member_number'] = member.get('member_number', '')
        session['last_login'] = get_current_utc_time().isoformat()
        session['requires_password_change'] = is_default

        # Update login timestamp
        try:
            supabase.table('members')\
                .update({'last_login': get_current_utc_time().isoformat()})\
                .eq('id', member['id'])\
                .execute()
        except Exception as e:
            print(f"Login timestamp update error: {e}")

        flash(f'Welcome {member["full_name"]}', 'success')
        
        # Redirect to password change if using default password
        if is_default:
            return redirect(url_for('memberauth.change_password'))
        
        return redirect(url_for('member.dashboard'))

    return render_template('member/login.html')

@memberauth_bp.route('/change-password', methods=['GET', 'POST'])
@member_login_required
def change_password():
    """Change password (required if using default password)"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not current_password or not new_password or not confirm_password:
            flash('All fields are required', 'error')
            return render_template('member/change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return render_template('member/change_password.html')
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('member/change_password.html')
        
        # Get member
        member = get_member_by_id(session['member_id'])
        if not member:
            flash('Member not found', 'error')
            return redirect(url_for('memberauth.member_login'))
        
        # Check current password
        password_correct, is_default = check_member_password(member, current_password)
        if not password_correct:
            flash('Current password is incorrect', 'error')
            return render_template('member/change_password.html')
        
        # Hash new password
        new_password_hash = generate_password_hash(new_password)
        
        # Update password in database
        try:
            supabase.table('members')\
                .update({
                    'password_hash': new_password_hash,
                    'default_password_used': False,
                    'updated_at': get_current_utc_time().isoformat()
                })\
                .eq('id', session['member_id'])\
                .execute()
            
            # Update session
            session['requires_password_change'] = False
            
            flash('Password changed successfully', 'success')
            return redirect(url_for('member.dashboard'))
            
        except Exception as e:
            flash('Failed to change password. Please try again.', 'error')
            print(f"Password change error: {e}")
            return render_template('member/change_password.html')
    
    return render_template('member/change_password.html')

@memberauth_bp.route('/update-password', methods=['GET', 'POST'])
@member_login_required
def update_password():
    """Optional password update for logged-in members"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not current_password or not new_password or not confirm_password:
            flash('All fields are required', 'error')
            return render_template('member/update_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return render_template('member/update_password.html')
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('member/update_password.html')
        
        # Get member
        member = get_member_by_id(session['member_id'])
        if not member:
            flash('Member not found', 'error')
            return redirect(url_for('memberauth.member_login'))
        
        # Check current password
        password_correct, _ = check_member_password(member, current_password)
        if not password_correct:
            flash('Current password is incorrect', 'error')
            return render_template('member/update_password.html')
        
        # Hash new password
        new_password_hash = generate_password_hash(new_password)
        
        # Update password in database
        try:
            supabase.table('members')\
                .update({
                    'password_hash': new_password_hash,
                    'default_password_used': False,
                    'updated_at': get_current_utc_time().isoformat()
                })\
                .eq('id', session['member_id'])\
                .execute()
            
            flash('Password updated successfully', 'success')
            return redirect(url_for('member.dashboard'))
            
        except Exception as e:
            flash('Failed to update password. Please try again.', 'error')
            print(f"Password update error: {e}")
            return render_template('member/update_password.html')
    
    return render_template('member/update_password.html')

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
            
            # You could create a function in sendotp.py for reset emails
            # send_password_reset_email(member['email'], reset_token, member['full_name'])
            
        except Exception as e:
            print(f"Reset token error: {e}")
        
        return render_template('member/forgot_password.html')
    
    return render_template('member/forgot_password.html')

@memberauth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password using token"""
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password or not confirm_password:
            flash('All fields are required', 'error')
            return render_template('member/reset_password.html', token=token)
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('member/reset_password.html', token=token)
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('member/reset_password.html', token=token)
        
        # Check token validity
        current_time = get_current_utc_time()
        try:
            token_res = supabase.table('password_resets')\
                .select('*')\
                .eq('reset_token', token)\
                .eq('used', False)\
                .gt('expires_at', current_time.isoformat())\
                .execute()
                
            if not token_res.data:
                flash('Invalid or expired reset token', 'error')
                return redirect(url_for('memberauth.forgot_password'))
                
            token_row = token_res.data[0]
            
        except Exception as e:
            flash('Error validating reset token', 'error')
            return redirect(url_for('memberauth.forgot_password'))
        
        # Hash new password
        new_password_hash = generate_password_hash(new_password)
        
        try:
            # Update member password
            supabase.table('members')\
                .update({
                    'password_hash': new_password_hash,
                    'default_password_used': False,
                    'updated_at': current_time.isoformat()
                })\
                .eq('id', token_row['member_id'])\
                .execute()
            
            # Mark token as used
            supabase.table('password_resets')\
                .update({'used': True})\
                .eq('id', token_row['id'])\
                .execute()
            
            flash('Password reset successfully. Please login with your new password.', 'success')
            return redirect(url_for('memberauth.member_login'))
            
        except Exception as e:
            flash('Failed to reset password. Please try again.', 'error')
            print(f"Password reset error: {e}")
            return render_template('member/reset_password.html', token=token)
    
    return render_template('member/reset_password.html', token=token)

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