import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from supabase import create_client, Client
from datetime import datetime, timedelta
import secrets
from send_otp import send_otp_email, save_otp_to_db, generate_otp, send_password_reset_email

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Create Blueprint
adminauth_bp = Blueprint('adminauth', __name__, url_prefix='/admin')

# Admin required decorator
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session.get('admin_logged_in'):
            flash('Please login to access this page', 'error')
            return redirect(url_for('adminauth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@adminauth_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember')
        
        # Validate inputs
        if not email or not password:
            flash('Email and password are required', 'error')
            return render_template('admin/login.html', email=email)
        
        try:
            # Check if admin exists in database
            response = supabase.table('admins').select('*').eq('email', email).eq('status', 'active').execute()
            
            if response.data and len(response.data) > 0:
                admin = response.data[0]
                
                # Verify password
                if check_password_hash(admin['password_hash'], password):
                    # Set session
                    session['admin_id'] = admin['id']
                    session['admin_email'] = admin['email']
                    session['admin_name'] = admin.get('name', 'Admin')
                    session['admin_role'] = admin.get('role', 'admin')
                    session['admin_logged_in'] = True
                    
                    # Update last login
                    supabase.table('admins').update({
                        'last_login': datetime.utcnow().isoformat(),
                        'login_count': admin.get('login_count', 0) + 1
                    }).eq('id', admin['id']).execute()
                    
                    # Set session expiration
                    if remember:
                        session.permanent = True
                    else:
                        session.permanent = False
                    
                    # Check if OTP is enabled and required
                    if admin.get('otp_enabled'):
                        # Generate and send OTP
                        otp_code = generate_otp()
                        save_otp_to_db(admin['id'], otp_code)
                        send_otp_email(admin['email'], otp_code, admin.get('name', 'Admin'))
                        
                        # Set OTP required flag in session
                        session['otp_required'] = True
                        session['otp_verified'] = False
                        
                        # Log OTP sent
                        log_admin_activity(admin['id'], 'otp_sent', 'OTP sent for login')
                        
                        flash('OTP has been sent to your email. Please verify to continue.', 'info')
                        return redirect(url_for('adminauth.verify_otp'))
                    
                    flash('Login successful!', 'success')
                    
                    # Log login activity
                    log_admin_activity(admin['id'], 'login', 'Admin logged in')
                    
                    return redirect(url_for('admin_dashboard'))
                else:
                    flash('Invalid email or password', 'error')
            else:
                flash('Admin account not found or inactive', 'error')
                
        except Exception as e:
            print(f"Login error: {e}")
            flash('An error occurred during login. Please try again.', 'error')
        
        return render_template('admin/login.html', email=email)
    
    return render_template('admin/login.html')

@adminauth_bp.route('/logout')
@admin_login_required
def admin_logout():
    # Log logout activity
    if 'admin_id' in session:
        log_admin_activity(session['admin_id'], 'logout', 'Admin logged out')
    
    # Clear session
    session.clear()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('adminauth.admin_login'))

@adminauth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email is required', 'error')
            return render_template('admin/forgot_password.html')
        
        try:
            # Check if admin exists
            response = supabase.table('admins').select('id, name, email').eq('email', email).eq('status', 'active').execute()
            
            if response.data and len(response.data) > 0:
                admin = response.data[0]
                
                # Generate password reset token
                reset_token = secrets.token_urlsafe(32)
                token_expiry = (datetime.utcnow() + timedelta(hours=1)).isoformat()
                
                # Save token to database
                supabase.table('password_resets').upsert({
                    'email': email,
                    'token': reset_token,
                    'expires_at': token_expiry,
                    'used': False
                }).execute()
                
                # Send password reset email
                reset_link = url_for('adminauth.reset_password', token=reset_token, _external=True)
                
                # Use the new function from send_otp.py
                send_password_reset_email(admin['email'], reset_link, admin.get('name', 'Admin'))
                
                # Log password reset request
                log_admin_activity(admin['id'], 'password_reset_request', 'Password reset requested')
                
                flash('Password reset instructions have been sent to your email', 'success')
                return render_template('admin/forgot_password.html', email_sent=True)
            else:
                flash('No admin account found with that email', 'error')
                
        except Exception as e:
            print(f"Forgot password error: {e}")
            flash('An error occurred. Please try again.', 'error')
    
    return render_template('admin/forgot_password.html')

@adminauth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('All fields are required', 'error')
            return render_template('admin/reset_password.html', token=token)
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('admin/reset_password.html', token=token)
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template('admin/reset_password.html', token=token)
        
        try:
            # Verify token
            response = supabase.table('password_resets').select('*').eq('token', token).eq('used', False).gte('expires_at', datetime.utcnow().isoformat()).execute()
            
            if response.data and len(response.data) > 0:
                reset_record = response.data[0]
                email = reset_record['email']
                
                # Update admin password
                password_hash = generate_password_hash(password)
                
                supabase.table('admins').update({
                    'password_hash': password_hash,
                    'updated_at': datetime.utcnow().isoformat()
                }).eq('email', email).execute()
                
                # Mark token as used
                supabase.table('password_resets').update({
                    'used': True,
                    'used_at': datetime.utcnow().isoformat()
                }).eq('token', token).execute()
                
                # Get admin ID for logging
                admin_response = supabase.table('admins').select('id').eq('email', email).execute()
                if admin_response.data:
                    admin_id = admin_response.data[0]['id']
                    log_admin_activity(admin_id, 'password_reset', 'Password reset successful')
                
                flash('Password reset successful! You can now login with your new password', 'success')
                return redirect(url_for('adminauth.admin_login'))
            else:
                flash('Invalid or expired reset link', 'error')
                return redirect(url_for('adminauth.forgot_password'))
                
        except Exception as e:
            print(f"Reset password error: {e}")
            flash('An error occurred. Please try again.', 'error')
    
    # GET request - verify token
    try:
        response = supabase.table('password_resets').select('email').eq('token', token).eq('used', False).gte('expires_at', datetime.utcnow().isoformat()).execute()
        
        if not response.data:
            flash('Invalid or expired reset link', 'error')
            return redirect(url_for('adminauth.forgot_password'))
    except Exception as e:
        print(f"Token verification error: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('adminauth.forgot_password'))
    
    return render_template('admin/reset_password.html', token=token)

@adminauth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    # Check if OTP is required
    if 'admin_id' not in session or not session.get('otp_required'):
        return redirect(url_for('adminauth.admin_login'))
    
    if request.method == 'POST':
        otp = request.form.get('otp', '').strip()
        
        if not otp or len(otp) != 6:
            flash('Please enter a valid 6-digit OTP', 'error')
            return render_template('admin/verify_otp.html')
        
        try:
            # Verify OTP from database
            response = supabase.table('admins').select('otp_code, otp_expires_at').eq('id', session['admin_id']).execute()
            
            if response.data and len(response.data) > 0:
                admin_otp = response.data[0]
                
                # Check if OTP exists and is valid
                if admin_otp.get('otp_code') and admin_otp.get('otp_expires_at'):
                    expiry_time = datetime.fromisoformat(admin_otp['otp_expires_at'].replace('Z', '+00:00'))
                    
                    if datetime.utcnow() > expiry_time:
                        flash('OTP has expired. Please request a new one.', 'error')
                        return render_template('admin/verify_otp.html')
                    
                    if admin_otp['otp_code'] == otp:
                        # Clear OTP from database
                        supabase.table('admins').update({
                            'otp_code': None,
                            'otp_expires_at': None
                        }).eq('id', session['admin_id']).execute()
                        
                        # Set OTP verified flag
                        session['otp_verified'] = True
                        session.pop('otp_required', None)
                        
                        # Log successful OTP verification
                        log_admin_activity(session['admin_id'], 'otp_verified', 'OTP verification successful')
                        
                        flash('OTP verified successfully!', 'success')
                        return redirect(url_for('admin_dashboard'))
                    else:
                        flash('Invalid OTP code', 'error')
                else:
                    flash('No valid OTP found. Please request a new one.', 'error')
            else:
                flash('Error verifying OTP. Please try again.', 'error')
                
        except Exception as e:
            print(f"OTP verification error: {e}")
            flash('An error occurred. Please try again.', 'error')
    
    return render_template('admin/verify_otp.html')

@adminauth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    if 'admin_id' not in session:
        return jsonify({'success': False, 'message': 'Session expired'}), 401
    
    try:
        # Get admin details
        response = supabase.table('admins').select('email, name').eq('id', session['admin_id']).execute()
        
        if response.data and len(response.data) > 0:
            admin = response.data[0]
            
            # Generate new OTP
            otp_code = generate_otp()
            
            # Save OTP to database
            save_otp_to_db(session['admin_id'], otp_code)
            
            # Send OTP email
            send_otp_email(admin['email'], otp_code, admin.get('name', 'Admin'))
            
            # Log OTP resend
            log_admin_activity(session['admin_id'], 'otp_resent', 'OTP resent')
            
            return jsonify({'success': True, 'message': 'OTP has been resent to your email'})
        else:
            return jsonify({'success': False, 'message': 'Admin not found'}), 404
            
    except Exception as e:
        print(f"Resend OTP error: {e}")
        return jsonify({'success': False, 'message': 'Failed to resend OTP'}), 500

# Utility functions
def log_admin_activity(admin_id, action, description, ip_address=None):
    """Log admin activities for security audit"""
    try:
        ip_address = ip_address or request.remote_addr if request else '127.0.0.1'
        
        supabase.table('admin_activities').insert({
            'admin_id': admin_id,
            'action': action,
            'description': description,
            'ip_address': ip_address,
            'user_agent': request.headers.get('User-Agent') if request else None,
            'created_at': datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        print(f"Failed to log activity: {e}")