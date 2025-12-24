import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from functools import wraps
from werkzeug.security import generate_password_hash
from supabase import create_client, Client
from datetime import datetime, timedelta
import uuid
import json
from decimal import Decimal
from cloudinary_upload import upload_member_document, validate_image_file
from pesapal import PesaPal
from werkzeug.utils import secure_filename
import shutil


# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Create Blueprint
members_bp = Blueprint('members', __name__, url_prefix='/admin/members')

# Admin required decorator
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session.get('admin_logged_in'):
            flash('Please login to access this page', 'error')
            return redirect(url_for('adminauth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# JSON encoder helper
class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal objects"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


@members_bp.before_request
def before_request():
    # Handle CORS for AJAX requests
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response
    if request.method == 'POST' and request.endpoint in ['members.process_cash_payment', 'members.process_pesapal_payment']:
        # Ensure JSON content type for these endpoints
        if request.is_json:
            return None
        
def create_member_accounts(member_id, member_data):
    """Create savings and loan accounts for a new member"""
    try:
        # Generate account numbers
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        savings_account_number = f"SAV{member_id[:8].upper()}{timestamp[-6:]}"
        loan_account_number = f"LOAN{member_id[:8].upper()}{timestamp[-6:]}"
        
        # Create savings account
        savings_data = {
            'member_id': member_id,
            'account_number': savings_account_number,
            'account_name': f"Savings - {member_data['full_name']}",
            'account_type': 'regular',
            'current_balance': 0.00,
            'available_balance': 0.00,
            'minimum_balance': 1000.00,
            'interest_rate': 3.00,
            'status': 'active',
            'opened_at': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        savings_response = supabase.table('savings_accounts').insert(savings_data).execute()
        
        if not savings_response.data:
            print(f"Failed to create savings account for member {member_id}")
            return False
        
        # Create loan account
        loan_data = {
            'member_id': member_id,
            'account_number': loan_account_number,
            'credit_limit': 100000.00,
            'current_balance': 0.00,
            'available_limit': 100000.00,
            'interest_rate': 12.00,
            'max_loan_amount': 5000000.00,
            'min_loan_amount': 10000.00,
            'repayment_period_months': 12,
            'status': 'active',
            'credit_score': 700,
            'opened_at': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        loan_response = supabase.table('loan_accounts').insert(loan_data).execute()
        
        if not loan_response.data:
            print(f"Failed to create loan account for member {member_id}")
            # Don't return False here, savings account was created successfully
        
        # Log account creation
        log_member_activity(member_id, 'accounts_created', 
                           f'Savings account {savings_account_number} and loan account {loan_account_number} created')
        
        print(f"Accounts created for member {member_id}: Savings: {savings_account_number}, Loan: {loan_account_number}")
        return True
        
    except Exception as e:
        print(f"Error creating accounts for member {member_id}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
# Routes
@members_bp.route('/add', methods=['GET', 'POST'])
@admin_login_required
def add_member():
    if request.method == 'POST':
        try:
            # Collect form data
            member_data = {
                'full_name': request.form.get('full_name', '').strip(),
                'email': request.form.get('email', '').strip().lower(),
                'phone_number': request.form.get('phone_number', '').strip(),
                'date_of_birth': request.form.get('date_of_birth', ''),
                'gender': request.form.get('gender', ''),
                'shares_owned': int(request.form.get('shares_owned', '0')),
                'nin_number': request.form.get('nin_number', '').strip(),
                'national_id': request.form.get('national_id', '').strip(),
                'contact_address': request.form.get('contact_address', '').strip(),
                'emergency_contact_name': request.form.get('emergency_contact_name', '').strip(),
                'emergency_contact_phone': request.form.get('emergency_contact_phone', '').strip(),
                'emergency_contact_relationship': request.form.get('emergency_contact_relationship', '').strip(),
                
                # Membership details - Use string instead of Decimal
                'membership_fee_amount': '50000.00',
                'registered_by': session.get('admin_id'),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Validate required fields
            required_fields = ['full_name', 'email', 'phone_number', 'date_of_birth']
            missing_fields = [field for field in required_fields if not member_data[field]]
            
            if missing_fields:
                flash(f"Missing required fields: {', '.join(missing_fields)}", 'error')
                return render_template('admin/members/add_member.html', form_data=member_data)
            
            # Validate email format
            if '@' not in member_data['email']:
                flash('Invalid email address', 'error')
                return render_template('admin/members/add_member.html', form_data=member_data)
            
            # Check if member already exists
            try:
                existing_member = supabase.table('members')\
                    .select('id')\
                    .or_(f"email.eq.{member_data['email']},phone_number.eq.{member_data['phone_number']}")\
                    .execute()
                
                if existing_member.data:
                    flash('Member with this email or phone number already exists', 'error')
                    return render_template('admin/members/add_member.html', form_data=member_data)
            except Exception as filter_error:
                # Fallback to checking each separately
                email_check = supabase.table('members').select('id').eq('email', member_data['email']).execute()
                phone_check = supabase.table('members').select('id').eq('phone_number', member_data['phone_number']).execute()
                
                if email_check.data or phone_check.data:
                    flash('Member with this email or phone number already exists', 'error')
                    return render_template('admin/members/add_member.html', form_data=member_data)
            
            # Generate unique ID for this registration
            registration_id = str(uuid.uuid4())
            
            # Create temp directory for file storage
            temp_dir = os.path.join('temp_uploads', registration_id)
            os.makedirs(temp_dir, exist_ok=True)
            
            # Handle file uploads - save to temporary storage
            file_fields = {
                'id_front': request.files.get('id_front'),
                'id_back': request.files.get('id_back'),
                'profile_photo': request.files.get('profile_photo')
            }
            
            uploaded_files_metadata = {}
            
            for field, file in file_fields.items():
                if file and file.filename:
                    is_valid, message = validate_image_file(file)
                    if not is_valid:
                        # Clean up temp directory
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        flash(f"Invalid {field}: {message}", 'error')
                        return render_template('admin/members/add_member.html', form_data=member_data)
                    
                    # Save file to temp directory
                    filename = secure_filename(f"{field}_{file.filename}")
                    filepath = os.path.join(temp_dir, filename)
                    file.save(filepath)
                    
                    uploaded_files_metadata[field] = {
                        'filename': filename,
                        'filepath': filepath,
                        'content_type': file.content_type,
                        'file_size': os.path.getsize(filepath)
                    }
            
            # Store minimal data in session
            session['pending_member'] = {
                'registration_id': registration_id,
                'member_data': member_data,
                'has_files': bool(uploaded_files_metadata)
            }
            
            # Save metadata to database or file for later retrieval
            registration_metadata = {
                'registration_id': registration_id,
                'member_data': member_data,
                'files_metadata': uploaded_files_metadata,
                'admin_id': session.get('admin_id'),
                'created_at': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(hours=24)).isoformat()  # 24-hour expiry
            }
            
            # Save to Supabase
            supabase.table('temp_registrations').insert(registration_metadata).execute()
            
            # Also save to local file as backup
            meta_file = os.path.join(temp_dir, 'metadata.json')
            with open(meta_file, 'w') as f:
                json.dump(registration_metadata, f, indent=2, default=str)
            
            # Redirect to payment selection
            return redirect(url_for('members.select_payment_method'))
            
        except Exception as e:
            print(f"Error in add_member: {e}")
            import traceback
            traceback.print_exc()
            flash('An error occurred while processing member information', 'error')
            return render_template('admin/members/add_member.html', form_data=member_data if 'member_data' in locals() else {})
    
    return render_template('admin/members/add_member.html')


@members_bp.route('/select-payment-method', methods=['GET', 'POST'])
@admin_login_required
def select_payment_method():
    if 'pending_member' not in session:
        flash('No pending member registration. Please start again.', 'error')
        return redirect(url_for('members.add_member'))
    
    registration_id = session['pending_member']['registration_id']
    
    # Verify registration still exists
    reg_data = supabase.table('temp_registrations')\
        .select('*')\
        .eq('registration_id', registration_id)\
        .eq('processed', False)\
        .single()\
        .execute()
    
    if not reg_data.data:
        flash('Registration session expired or not found. Please start again.', 'error')
        session.pop('pending_member', None)
        return redirect(url_for('members.add_member'))
    
    if request.method == 'POST':
        payment_method = request.form.get('payment_method')
        
        if payment_method == 'cash':
            # Process cash payment immediately
            return process_cash_payment()
        elif payment_method == 'pesapal':
            # Process PesaPal payment
            return process_pesapal_payment()
        else:
            flash('Invalid payment method selected', 'error')
    
    # GET request - show payment method selection
    member_data = reg_data.data['member_data']
    return render_template('admin/members/select_payment.html', 
                          member_name=member_data.get('full_name'),
                          membership_fee=50000,
                          registration_id=registration_id)
@members_bp.route('/process-cash-payment', methods=['POST'])

@members_bp.route('/process-cash-payment', methods=['POST'])
@admin_login_required
def process_cash_payment():
    try:
        # Parse JSON data
        if request.is_json:
            data = request.get_json()
            registration_id = data.get('registration_id') if data else None
        else:
            # Fallback to form data
            registration_id = request.form.get('registration_id')
        
        if not registration_id:
            return jsonify({'success': False, 'message': 'Registration ID required'}), 400
        
        # Get registration data
        reg_data = supabase.table('temp_registrations')\
            .select('*')\
            .eq('registration_id', registration_id)\
            .eq('processed', False)\
            .single()\
            .execute()
        
        if not reg_data.data:
            return jsonify({'success': False, 'message': 'Registration not found or already processed'}), 400
        
        registration = reg_data.data
        member_data = registration['member_data']
        
        # Convert Decimal to string for Supabase insertion
        if isinstance(member_data.get('membership_fee_amount'), (int, float, Decimal)):
            member_data['membership_fee_amount'] = str(member_data['membership_fee_amount'])
        
        # Mark membership as paid
        member_data['membership_fee_paid'] = True
        member_data['membership_paid_at'] = datetime.now().isoformat()
        
        # Clean up the member_data for Supabase insertion
        # Ensure all values are JSON serializable
        clean_member_data = {}
        for key, value in member_data.items():
            if isinstance(value, Decimal):
                clean_member_data[key] = str(value)
            elif isinstance(value, datetime):
                clean_member_data[key] = value.isoformat()
            elif isinstance(value, uuid.UUID):
                clean_member_data[key] = str(value)
            else:
                clean_member_data[key] = value
        
        # Insert member into database
        response = supabase.table('members').insert(clean_member_data).execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Failed to save member data'}), 500
        
        member_id = response.data[0]['id']
        member_number = response.data[0]['member_number']
        
        # CREATE SAVINGS AND LOAN ACCOUNTS
        create_member_accounts(member_id, member_data)
        
        # Create payment record
        payment_data = {
            'member_id': member_id,
            'payment_method': 'cash',
            'amount': 50000.00,
            'currency': 'UGX',
            'payment_status': 'completed',
            'reference_number': f"CASH-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'confirmed_by': session.get('admin_id'),
            'confirmed_at': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat()
        }
        
        supabase.table('membership_payments').insert(payment_data).execute()
        
        # Handle file uploads if they exist
        files_metadata = registration.get('files_metadata', {})
        temp_dir = os.path.join('temp_uploads', registration_id)
        
        for field, file_info in files_metadata.items():
            filepath = file_info.get('filepath')
            
            if filepath and os.path.exists(filepath):
                # Upload to Cloudinary
                try:
                    with open(filepath, 'rb') as f:
                        upload_result = upload_member_document(f, member_id, field)
                    
                    if upload_result:
                        # Save to member_documents table
                        doc_data = {
                            'member_id': member_id,
                            'document_type': field,
                            'cloudinary_public_id': upload_result['public_id'],
                            'cloudinary_url': upload_result['secure_url'],
                            'file_name': file_info['filename'],
                            'file_size': file_info['file_size'],
                            'file_type': file_info['content_type'],
                            'created_at': datetime.now().isoformat()
                        }
                        
                        supabase.table('member_documents').insert(doc_data).execute()
                        
                        # Update member record with URL
                        update_data = {}
                        if field == 'profile_photo':
                            update_data['profile_photo_url'] = upload_result['secure_url']
                        elif field == 'id_front':
                            update_data['id_front_url'] = upload_result['secure_url']
                        elif field == 'id_back':
                            update_data['id_back_url'] = upload_result['secure_url']
                        
                        if update_data:
                            supabase.table('members').update(update_data).eq('id', member_id).execute()
                except Exception as e:
                    print(f"Error uploading file {field}: {e}")
                    # Continue with other files even if one fails
        
        # Clean up temp files
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                print(f"Error cleaning up temp directory {temp_dir}: {e}")
        
        # Mark registration as processed
        supabase.table('temp_registrations')\
            .update({'processed': True})\
            .eq('registration_id', registration_id)\
            .execute()
        
        # Clear session data
        session.pop('pending_member', None)
        
        # Log successful registration
        log_member_activity(member_id, 'registration_completed', 
                           f'Member registered successfully with cash payment. Member Number: {member_number}')
        
        return jsonify({
            'success': True,
            'message': 'Member registered successfully with cash payment',
            'member_number': member_number,
            'member_id': member_id,
            'redirect_url': url_for('members.member_details', member_id=member_id)
        })
        
    except Exception as e:
        print(f"Error in process_cash_payment: {e}")
        import traceback
        traceback.print_exc()
        
        # Clean up temp files on error too
        registration_id = request.form.get('registration_id') or (request.get_json(silent=True) or {}).get('registration_id')
        if registration_id:
            temp_dir = os.path.join('temp_uploads', registration_id)
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as cleanup_error:
                    print(f"Error cleaning up temp directory on error: {cleanup_error}")
        
        return jsonify({'success': False, 'message': f'Error processing cash payment: {str(e)}'}), 500
    
@members_bp.route('/process-pesapal-payment', methods=['POST'])
@admin_login_required
def process_pesapal_payment():
    try:
        # Parse JSON data
        if request.is_json:
            data = request.get_json()
            registration_id = data.get('registration_id') if data else None
        else:
            # Fallback to form data
            registration_id = request.form.get('registration_id')
        
        if not registration_id:
            return jsonify({'success': False, 'message': 'Registration ID required'}), 400
        
        # Get registration data
        reg_data = supabase.table('temp_registrations')\
            .select('*')\
            .eq('registration_id', registration_id)\
            .eq('processed', False)\
            .single()\
            .execute()
        
        if not reg_data.data:
            return jsonify({'success': False, 'message': 'Registration not found or already processed'}), 400
        
        registration = reg_data.data
        member_data = registration['member_data']
        
        # Generate temporary member ID for payment reference
        temp_member_id = str(uuid.uuid4())
        
        # Store pending member data with temp ID in database
        payment_session_data = {
            'temp_member_id': temp_member_id,
            'registration_id': registration_id,
            'member_data': member_data,
            'files_metadata': registration.get('files_metadata', {}),
            'admin_id': session.get('admin_id'),
            'created_at': datetime.now().isoformat()
        }
        
        supabase.table('payment_sessions').insert(payment_session_data).execute()
        
        # Initialize PesaPal
        pesapal = PesaPal()
        
        # Prepare payment details
        amount = 15000
        reference_id = f"MEM-{temp_member_id[:8].upper()}"
        
        # Extract names for billing
        names = member_data['full_name'].split()
        first_name = names[0] if names else "Member"
        last_name = names[-1] if len(names) > 1 else "User"
        
        # Get callback URL
        callback_url = url_for('members.pesapal_callback', _external=True)
        
        # Submit order to PesaPal
        order = pesapal.submit_order(
            amount=amount,
            reference_id=reference_id,
            callback_url=callback_url,
            email=member_data['email'],
            first_name=first_name,
            last_name=last_name
        )
        
        if order and 'redirect_url' in order:
            # Update payment session with order info
            supabase.table('payment_sessions')\
                .update({
                    'order_tracking_id': order['order_tracking_id'],
                    'reference_id': reference_id,
                    'amount': amount
                })\
                .eq('temp_member_id', temp_member_id)\
                .execute()
            
            return jsonify({
                'success': True,
                'redirect_url': order['redirect_url'],
                'order_id': order['order_tracking_id']
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to initiate PesaPal payment'}), 500
            
    except Exception as e:
        print(f"Error in process_pesapal_payment: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error processing PesaPal payment: {str(e)}'}), 500

def create_member_accounts(member_id, member_data):
    """Create savings and loan accounts for a new member"""
    try:
        # Generate account numbers
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        savings_account_number = f"SAV{member_id[:8].upper()}{timestamp[-6:]}"
        loan_account_number = f"LOAN{member_id[:8].upper()}{timestamp[-6:]}"
        
        # Create savings account
        savings_data = {
            'member_id': member_id,
            'account_number': savings_account_number,
            'account_name': f"Savings - {member_data['full_name']}",
            'account_type': 'regular',
            'current_balance': 0.00,
            'available_balance': 0.00,
            'minimum_balance': 1000.00,
            'interest_rate': 3.00,
            'status': 'active',
            'opened_at': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        savings_response = supabase.table('savings_accounts').insert(savings_data).execute()
        
        if not savings_response.data:
            print(f"Failed to create savings account for member {member_id}")
            return False
        
        # Create loan account
        loan_data = {
            'member_id': member_id,
            'account_number': loan_account_number,
            'credit_limit': 100000.00,
            'current_balance': 0.00,
            'available_limit': 100000.00,
            'interest_rate': 12.00,
            'max_loan_amount': 5000000.00,
            'min_loan_amount': 10000.00,
            'repayment_period_months': 12,
            'status': 'active',
            'credit_score': 700,
            'opened_at': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        loan_response = supabase.table('loan_accounts').insert(loan_data).execute()
        
        if not loan_response.data:
            print(f"Failed to create loan account for member {member_id}")
            # Don't return False here, savings account was created successfully
        
        # Log account creation
        log_member_activity(member_id, 'accounts_created', 
                           f'Savings account {savings_account_number} and loan account {loan_account_number} created')
        
        print(f"Accounts created for member {member_id}: Savings: {savings_account_number}, Loan: {loan_account_number}")
        return True
        
    except Exception as e:
        print(f"Error creating accounts for member {member_id}: {e}")
        import traceback
        traceback.print_exc()
        return False

@members_bp.route('/pesapal-callback', methods=['GET'])
def pesapal_callback():
    try:
        order_tracking_id = request.args.get('OrderTrackingId')
        
        if not order_tracking_id:
            flash('Invalid payment callback', 'error')
            return redirect(url_for('members.add_member'))
        
        # Verify payment with PesaPal
        pesapal = PesaPal()
        payment_status = pesapal.verify_transaction_status(order_tracking_id)
        
        if not payment_status:
            flash('Could not verify payment status', 'error')
            return redirect(url_for('members.add_member'))
        
        # Get payment session from database
        payment_session_res = supabase.table('payment_sessions')\
            .select('*')\
            .eq('order_tracking_id', order_tracking_id)\
            .single()\
            .execute()
        
        if not payment_session_res.data:
            flash('Payment session not found', 'error')
            return redirect(url_for('members.add_member'))
        
        payment_session = payment_session_res.data
        temp_member_id = payment_session['temp_member_id']
        registration_id = payment_session['registration_id']
        
        # Get registration data
        reg_data = supabase.table('temp_registrations')\
            .select('*')\
            .eq('registration_id', registration_id)\
            .eq('processed', False)\
            .single()\
            .execute()
        
        if not reg_data.data:
            flash('Registration data not found', 'error')
            return redirect(url_for('members.add_member'))
        
        registration = reg_data.data
        member_data = registration['member_data']
        files_metadata = registration.get('files_metadata', {})
        
        # Normalize payment status
        payment_status_desc = payment_status.get('payment_status_description', '').upper()
        if 'COMPLETED' in payment_status_desc:
            normalized_status = 'completed'
        elif 'PENDING' in payment_status_desc:
            normalized_status = 'pending'
        else:
            normalized_status = 'failed'
        
        if normalized_status == 'completed':
            # Clean up the member_data for Supabase insertion
            # Ensure all values are JSON serializable
            clean_member_data = {}
            for key, value in member_data.items():
                if isinstance(value, Decimal):
                    clean_member_data[key] = str(value)
                elif isinstance(value, datetime):
                    clean_member_data[key] = value.isoformat()
                elif isinstance(value, uuid.UUID):
                    clean_member_data[key] = str(value)
                else:
                    clean_member_data[key] = value
            
            # Update member data with payment info
            clean_member_data['membership_fee_paid'] = True
            clean_member_data['membership_paid_at'] = datetime.now().isoformat()
            clean_member_data['registered_by'] = payment_session.get('admin_id')
            
            # Insert member into database
            response = supabase.table('members').insert(clean_member_data).execute()
            
            if not response.data:
                flash('Failed to save member data', 'error')
                return redirect(url_for('members.add_member'))
            
            member_id = response.data[0]['id']
            member_number = response.data[0]['member_number']
            
            # CREATE SAVINGS AND LOAN ACCOUNTS
            create_member_accounts(member_id, member_data)
            
            # Create payment record
            payment_record = {
                'member_id': member_id,
                'payment_method': 'pesapal',
                'amount': 50000.00,
                'currency': 'UGX',
                'payment_status': 'completed',
                'transaction_id': order_tracking_id,
                'pesapal_order_id': payment_status.get('order_tracking_id'),
                'pesapal_tracking_id': order_tracking_id,
                'pesapal_response': payment_status,
                'payment_date': datetime.now().isoformat(),
                'created_at': datetime.now().isoformat()
            }
            
            supabase.table('membership_payments').insert(payment_record).execute()
            
            # Handle file uploads
            temp_dir = os.path.join('temp_uploads', registration_id)
            
            for field, file_info in files_metadata.items():
                filepath = file_info.get('filepath')
                
                if filepath and os.path.exists(filepath):
                    # Upload to Cloudinary
                    try:
                        with open(filepath, 'rb') as f:
                            upload_result = upload_member_document(f, member_id, field)
                        
                        if upload_result:
                            # Save to member_documents table
                            doc_data = {
                                'member_id': member_id,
                                'document_type': field,
                                'cloudinary_public_id': upload_result['public_id'],
                                'cloudinary_url': upload_result['secure_url'],
                                'file_name': file_info['filename'],
                                'file_size': file_info['file_size'],
                                'file_type': file_info['content_type'],
                                'created_at': datetime.now().isoformat()
                            }
                            
                            supabase.table('member_documents').insert(doc_data).execute()
                            
                            # Update member record with URL
                            update_data = {}
                            if field == 'profile_photo':
                                update_data['profile_photo_url'] = upload_result['secure_url']
                            elif field == 'id_front':
                                update_data['id_front_url'] = upload_result['secure_url']
                            elif field == 'id_back':
                                update_data['id_back_url'] = upload_result['secure_url']
                            
                            if update_data:
                                supabase.table('members').update(update_data).eq('id', member_id).execute()
                    except Exception as e:
                        print(f"Error uploading file {field}: {e}")
                        # Continue with other files even if one fails
            
            # Clean up temp files
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    print(f"Error cleaning up temp directory {temp_dir}: {e}")
            
            # Mark registration as processed
            supabase.table('temp_registrations')\
                .update({'processed': True})\
                .eq('registration_id', registration_id)\
                .execute()
            
            # Clear payment session
            supabase.table('payment_sessions')\
                .delete()\
                .eq('temp_member_id', temp_member_id)\
                .execute()
            
            # Clear session data
            session.pop('temp_member_id', None)
            session.pop('pending_member', None)
            
            flash(f'Member registered successfully! Member Number: {member_number}', 'success')
            return redirect(url_for('members.member_details', member_id=member_id))
        
        elif normalized_status == 'pending':
            flash('Payment is pending confirmation. Member registration will be completed once payment is confirmed.', 'info')
            return redirect(url_for('members.add_member'))
        
        else:
            flash('Payment failed. Please try again or use a different payment method.', 'error')
            return redirect(url_for('members.add_member'))
            
    except Exception as e:
        print(f"Error in pesapal_callback: {e}")
        import traceback
        traceback.print_exc()
        flash('Error processing payment callback', 'error')
        return redirect(url_for('members.add_member'))
    
    
@members_bp.route('/members')
@admin_login_required
def members_list():
    try:
        # Get search parameters
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        
        # Build initial query
        query = supabase.table('members').select('*')
        
        if search:
            # Build OR query manually
            try:
                # Try using or_ method if available
                query = query.or_(f'full_name.ilike.%{search}%,email.ilike.%{search}%,phone_number.ilike.%{search}%,member_number.ilike.%{search}%')
            except AttributeError:
                # If or_ doesn't exist, use multiple queries and combine
                # First, get all members
                all_members = query.execute()
                
                if all_members.data:
                    # Filter in Python
                    search_lower = search.lower()
                    filtered_members = []
                    for member in all_members.data:
                        if (search_lower in member.get('full_name', '').lower() or
                            search_lower in member.get('email', '').lower() or
                            search_lower in member.get('phone_number', '').lower() or
                            search_lower in member.get('member_number', '').lower()):
                            filtered_members.append(member)
                    
                    members = filtered_members
                else:
                    members = []
                
                # Apply status filter if needed
                if status:
                    members = [m for m in members if m.get('account_status') == status]
                
                # Sort by created_at descending
                members.sort(key=lambda x: x.get('created_at', ''), reverse=True)
                
                return render_template('admin/members/list.html', 
                                     members=members,
                                     search=search,
                                     status=status,
                                     total_count=len(members))
        
        if status:
            query = query.eq('account_status', status)
        
        # Order by created_at descending
        query = query.order('created_at', desc=True)
        
        response = query.execute()
        members = response.data if response.data else []
        
        # Get counts for status filter
        counts_response = supabase.table('members').select('account_status', count='exact').execute()
        
        return render_template('admin/members/list.html', 
                             members=members,
                             search=search,
                             status=status,
                             total_count=len(members))
        
    except Exception as e:
        print(f"Error fetching members list: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading members list', 'error')
        return render_template('admin/members/list.html', members=[], search=search, status=status, total_count=0)

@members_bp.route('/member/<member_id>')
@admin_login_required
def member_details(member_id):
    try:
        # Get member details
        member_res = supabase.table('members').select('*').eq('id', member_id).single().execute()
        members = supabase.table('members') \
            .select('id, full_name, shares_owned') \
            .eq('id', member_id) \
            .single() \
            .execute()
            
        # Fetch all loans for a specific member
        loans_response = supabase.table('loan_accounts') \
            .select('*') \
            .eq('member_id', member_id) \
            .execute()

        # Extract data
        member_loans = loans_response.data if loans_response.data else []
        
        if not member_res.data:
            flash('Member not found', 'error')
            return redirect(url_for('members.members_list'))
        
        member = member_res.data
        
        # Get savings account
        savings_res = supabase.table('savings_accounts').select('*').eq('member_id', member_id).execute()
        savings_account = savings_res.data[0] if savings_res.data else None
        
        # Get loan account
        loans_res = supabase.table('loan_accounts').select('*').eq('member_id', member_id).execute()
        loan_account = loans_res.data[0] if loans_res.data else None
        
        # Get documents
        docs_res = supabase.table('member_documents').select('*').eq('member_id', member_id).execute()
        documents = docs_res.data if docs_res.data else []
        
        # Get membership payment history
        membership_payments_res = supabase.table('membership_payments').select('*').eq('member_id', member_id).order('created_at', desc=True).execute()
        membership_payments = membership_payments_res.data if membership_payments_res.data else []
        
        # Get loan repayment history
        loan_repayments_res = supabase.table('loan_repayments')\
            .select('*, loan_applications(account_number, loan_amount)')\
            .eq('member_id', member_id)\
            .order('paid_date', desc=True)\
            .order('due_date', desc=True)\
            .execute()
        
        loan_repayments = loan_repayments_res.data if loan_repayments_res.data else []
        
        # Get loan transactions history
        loan_transactions_res = supabase.table('loan_transactions')\
            .select('*')\
            .eq('loan_account_id', loan_account['id'] if loan_account else None)\
            .order('created_at', desc=True)\
            .execute()
        
        loan_transactions = loan_transactions_res.data if loan_transactions_res.data else []
        
        # Combine all payments for display
        all_payments = []
        
        # Add membership payments
        for payment in membership_payments:
            all_payments.append({
                'type': 'membership',
                'date': payment.get('created_at'),
                'method': payment.get('payment_method'),
                'amount': payment.get('amount'),
                'status': payment.get('payment_status'),
                'reference': payment.get('reference_number'),
                'description': 'Membership Fee Payment'
            })
        
        # Add loan repayments
        for repayment in loan_repayments:
            if repayment.get('paid_amount') and float(repayment.get('paid_amount', 0)) > 0:
                loan_app = repayment.get('loan_applications', {})
                all_payments.append({
                    'type': 'loan_repayment',
                    'date': repayment.get('paid_date') or repayment.get('created_at'),
                    'method': repayment.get('payment_method'),
                    'amount': repayment.get('paid_amount'),
                    'status': 'completed' if repayment.get('status') == 'paid' else 'pending',
                    'reference': repayment.get('reference_number'),
                    'description': f'Loan Repayment - Installment #{repayment.get("installment_number")}',
                    'loan_account': loan_app.get('account_number') if loan_app else 'N/A'
                })
        
        # Add loan transactions (disbursements, etc.)
        for transaction in loan_transactions:
            transaction_type_display = transaction.get('transaction_type', '').replace('_', ' ').title()
            all_payments.append({
                'type': 'loan_transaction',
                'date': transaction.get('created_at'),
                'method': transaction.get('payment_method'),
                'amount': transaction.get('amount'),
                'status': 'completed',
                'reference': transaction.get('reference_number'),
                'description': f'Loan {transaction_type_display}',
                'balance_before': transaction.get('balance_before'),
                'balance_after': transaction.get('balance_after')
            })
        
        # Sort all payments by date (newest first)
        all_payments.sort(key=lambda x: x.get('date') or '', reverse=True)
        
        return render_template('admin/members/details.html',
                             member=member,
                             savings_account=savings_account,
                             loan_account=loan_account,
                             documents=documents,
                             payments=all_payments,  # Changed from membership_payments to all_payments
                             shares_owned=members.data.get('shares_owned') if members.data else 0,
                             member_loans=member_loans,
                             membership_payments_count=len(membership_payments),
                             loan_repayments_count=len([r for r in loan_repayments if r.get('paid_amount')]),
                             loan_transactions_count=len(loan_transactions))
        
    except Exception as e:
        print(f"Error fetching member details: {e}")
        flash('Error loading member details', 'error')
        return redirect(url_for('members.members_list'))
    
    
 

@members_bp.route('/member/<member_id>/reset-password', methods=['POST'])
@admin_login_required
def reset_member_password(member_id):
    try:
        # Reset to default password '123'
        default_password_hash = generate_password_hash('123')
        
        supabase.table('members').update({
            'password_hash': default_password_hash,
            'default_password_used': True,
            'updated_at': datetime.now().isoformat()
        }).eq('id', member_id).execute()
        
        # Log activity
        log_member_activity(member_id, 'password_reset', 'Password reset to default by admin')
        
        flash('Password reset to default (123) successfully', 'success')
        return redirect(url_for('members.member_details', member_id=member_id))
        
    except Exception as e:
        print(f"Error resetting password: {e}")
        flash('Error resetting password', 'error')
        return redirect(url_for('members.member_details', member_id=member_id))

@members_bp.route('/member/<member_id>/update-status', methods=['POST'])
@admin_login_required
def update_member_status(member_id):
    try:
        new_status = request.form.get('status')
        
        if new_status not in ['active', 'suspended', 'terminated']:
            flash('Invalid status', 'error')
            return redirect(url_for('members.member_details', member_id=member_id))
        
        supabase.table('members').update({
            'account_status': new_status,
            'updated_at': datetime.now().isoformat()
        }).eq('id', member_id).execute()
        
        # Log activity
        log_member_activity(member_id, 'status_update', f'Status changed to {new_status}')
        
        flash(f'Member status updated to {new_status}', 'success')
        return redirect(url_for('members.member_details', member_id=member_id))
        
    except Exception as e:
        print(f"Error updating status: {e}")
        flash('Error updating status', 'error')
        return redirect(url_for('members.member_details', member_id=member_id))

# Utility functions
def log_member_activity(member_id, action, description):
    """Log member activities"""
    try:
        supabase.table('member_audit_log').insert({
            'member_id': member_id,
            'action': action,
            'description': description,
            'performed_by': session.get('admin_id'),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'created_at': datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"Failed to log activity: {e}")

def check_membership_expiry():
    """Check and update expired memberships"""
    try:
        # Find members whose membership has expired
        today = datetime.now().isoformat()
        
        expired_members = supabase.table('members')\
            .select('id, member_number, full_name, membership_expires_at')\
            .lt('membership_expires_at', today)\
            .eq('membership_fee_paid', True)\
            .eq('account_status', 'active')\
            .execute()
        
        if expired_members.data:
            for member in expired_members.data:
                # Update member status
                supabase.table('members').update({
                    'membership_fee_paid': False,
                    'account_status': 'suspended',
                    'updated_at': datetime.now().isoformat()
                }).eq('id', member['id']).execute()
                
                # Log activity
                log_member_activity(member['id'], 'membership_expired', 
                                   f'Membership expired on {member["membership_expires_at"]}')
                
                print(f"Membership expired for {member['member_number']} - {member['full_name']}")
        
        return len(expired_members.data) if expired_members.data else 0
    except Exception as e:
        print(f"Error checking membership expiry: {e}")
        return 0

def cleanup_temp_files():
    """Clean up temp files older than 24 hours"""
    try:
        temp_base = 'temp_uploads'
        if not os.path.exists(temp_base):
            return
        
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for dir_name in os.listdir(temp_base):
            dir_path = os.path.join(temp_base, dir_name)
            if os.path.isdir(dir_path):
                # Check creation time
                dir_time = datetime.fromtimestamp(os.path.getctime(dir_path))
                if dir_time < cutoff_time:
                    shutil.rmtree(dir_path, ignore_errors=True)
                    print(f"Cleaned up old temp directory: {dir_path}")
    except Exception as e:
        print(f"Error cleaning up temp files: {e}")

# Register cleanup on exit
import atexit
atexit.register(cleanup_temp_files)

# Also add a route to manually trigger cleanup
@members_bp.route('/cleanup-temp-files')
def cleanup_temp_files_endpoint():
    """Endpoint to manually clean up temp files"""
    try:
        cleanup_temp_files()
        
        # Also clean up expired database records
        supabase.table('temp_registrations')\
            .delete()\
            .lt('expires_at', datetime.now().isoformat())\
            .execute()
        
        # Clean up old payment sessions
        supabase.table('payment_sessions')\
            .delete()\
            .lt('created_at', (datetime.now() - timedelta(hours=24)).isoformat())\
            .execute()
        
        return jsonify({'success': True, 'message': 'Cleanup completed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Scheduled task to check membership expiry (can be run via cron)
@members_bp.route('/check-expiry')
def check_expiry_endpoint():
    """Endpoint to manually trigger membership expiry check"""
    try:
        if 'admin_logged_in' not in session:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
        expired_count = check_membership_expiry()
        return jsonify({
            'success': True,
            'message': f'Checked membership expiry. {expired_count} members expired.'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500