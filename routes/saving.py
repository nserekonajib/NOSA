import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from supabase import create_client, Client
from datetime import datetime, timedelta
import uuid
import json
from decimal import Decimal
from cloudinary_upload import validate_image_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import shutil
from pesapal import PesaPal

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Create Blueprint
savings_bp = Blueprint('savings', __name__, url_prefix='/admin/savings')

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

# Routes
@savings_bp.route('/accounts')
@admin_login_required
def accounts():
    """View all savings accounts"""
    try:
        # Get search parameters
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        
        # Build query with member information
        query = supabase.table('savings_accounts')\
            .select('*, members(full_name, email, phone_number, member_number)')\
            .order('created_at', desc=True)
        
        if status:
            query = query.eq('status', status)
        
        response = query.execute()
        accounts_data = response.data if response.data else []
        
        # Apply search filter in Python
        if search:
            search_lower = search.lower()
            filtered_accounts = []
            for account in accounts_data:
                member_info = account.get('members', {})
                if (search_lower in account.get('account_number', '').lower() or
                    search_lower in member_info.get('full_name', '').lower() or
                    search_lower in member_info.get('email', '').lower() or
                    search_lower in member_info.get('phone_number', '').lower() or
                    search_lower in member_info.get('member_number', '').lower()):
                    filtered_accounts.append(account)
            accounts_data = filtered_accounts
        
        # Calculate totals
        total_balance = sum(Decimal(str(acc.get('current_balance', 0))) for acc in accounts_data)
        total_accounts = len(accounts_data)
        active_accounts = len([acc for acc in accounts_data if acc.get('status') == 'active'])
        
        return render_template('admin/savings/accounts.html',
                             accounts=accounts_data,
                             search=search,
                             status=status,
                             total_balance=total_balance,
                             total_accounts=total_accounts,
                             active_accounts=active_accounts)
        
    except Exception as e:
        print(f"Error fetching savings accounts: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading savings accounts', 'error')
        return render_template('admin/savings/accounts.html',
                             accounts=[],
                             search=search,
                             status=status,
                             total_balance=0,
                             total_accounts=0,
                             active_accounts=0)

@savings_bp.route('/account/<account_id>')
@admin_login_required
def account_details(account_id):
    """View savings account details"""
    try:
        # Get account details with member info
        account_res = supabase.table('savings_accounts')\
            .select('*, members(*)')\
            .eq('id', account_id)\
            .single()\
            .execute()
        
        if not account_res.data:
            flash('Savings account not found', 'error')
            return redirect(url_for('savings.accounts'))
        
        account = account_res.data
        member = account.get('members', {})
        
        # Get transaction history
        transactions_res = supabase.table('savings_transactions')\
            .select('*')\
            .eq('savings_account_id', account_id)\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        
        # Get deposit requests
        deposits_res = supabase.table('deposit_requests')\
            .select('*')\
            .eq('savings_account_id', account_id)\
            .order('created_at', desc=True)\
            .limit(20)\
            .execute()
        
        deposits = deposits_res.data if deposits_res.data else []
        
        # Get withdrawal requests
        withdrawals_res = supabase.table('withdrawal_requests')\
            .select('*')\
            .eq('savings_account_id', account_id)\
            .order('created_at', desc=True)\
            .limit(20)\
            .execute()
        
        withdrawals = withdrawals_res.data if withdrawals_res.data else []
        
        return render_template('admin/savings/account_details.html',
                             account=account,
                             member=member,
                             transactions=transactions,
                             deposits=deposits,
                             withdrawals=withdrawals)
        
    except Exception as e:
        print(f"Error fetching account details: {e}")
        flash('Error loading account details', 'error')
        return redirect(url_for('savings.accounts'))

@savings_bp.route('/deposits')
@admin_login_required
def deposits():
    """View and manage deposit requests"""
    try:
        # Get filter parameters
        status = request.args.get('status', '')
        search = request.args.get('search', '')
        
        # Build query
        query = supabase.table('deposit_requests')\
            .select('*, savings_accounts(*, members(full_name, member_number))')\
            .order('created_at', desc=True)
        
        if status:
            query = query.eq('status', status)
        
        response = query.execute()
        deposits = response.data if response.data else []
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            filtered_deposits = []
            for deposit in deposits:
                account_info = deposit.get('savings_accounts', {})
                member_info = account_info.get('members', {})
                if (search_lower in deposit.get('reference_number', '').lower() or
                    search_lower in member_info.get('full_name', '').lower() or
                    search_lower in member_info.get('member_number', '').lower()):
                    filtered_deposits.append(deposit)
            deposits = filtered_deposits
        
        # Calculate statistics
        total_deposits = len(deposits)
        pending_deposits = len([d for d in deposits if d.get('status') == 'pending'])
        completed_deposits = len([d for d in deposits if d.get('status') == 'completed'])
        
        return render_template('admin/savings/deposits.html',
                             deposits=deposits,
                             status=status,
                             search=search,
                             total_deposits=total_deposits,
                             pending_deposits=pending_deposits,
                             completed_deposits=completed_deposits)
        
    except Exception as e:
        print(f"Error fetching deposits: {e}")
        flash('Error loading deposit requests', 'error')
        return render_template('admin/savings/deposits.html',
                             deposits=[],
                             status=status,
                             search=search,
                             total_deposits=0,
                             pending_deposits=0,
                             completed_deposits=0)

@savings_bp.route('/deposit/new', methods=['GET', 'POST'])
@admin_login_required
def new_deposit():
    """Create a new deposit request"""
    if request.method == 'POST':
        try:
            # Get form data
            savings_account_id = request.form.get('savings_account_id')
            amount = Decimal(request.form.get('amount', '0'))
            payment_method = request.form.get('payment_method')
            description = request.form.get('description', '').strip()
            
            if not savings_account_id or amount <= 0:
                flash('Invalid deposit details', 'error')
                return redirect(url_for('savings.new_deposit'))
            
            # Get account details
            account_res = supabase.table('savings_accounts')\
                .select('*, members(*)')\
                .eq('id', savings_account_id)\
                .single()\
                .execute()
            
            if not account_res.data:
                flash('Savings account not found', 'error')
                return redirect(url_for('savings.new_deposit'))
            
            account = account_res.data
            
            # Create deposit request
            deposit_data = {
                'savings_account_id': savings_account_id,
                'member_id': account['member_id'],
                'amount': float(amount),
                'currency': 'UGX',
                'payment_method': payment_method,
                'description': description,
                'reference_number': f"DEP{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}",
                'status': 'pending' if payment_method == 'pesapal' else 'processing',
                'requested_by': session.get('admin_id'),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # If cash payment, process immediately
            if payment_method == 'cash':
                deposit_data['status'] = 'processing'
                deposit_data['confirmed_by'] = session.get('admin_id')
                deposit_data['confirmed_at'] = datetime.now().isoformat()
            
            # Insert deposit request
            response = supabase.table('deposit_requests').insert(deposit_data).execute()
            
            if not response.data:
                flash('Failed to create deposit request', 'error')
                return redirect(url_for('savings.new_deposit'))
            
            deposit_id = response.data[0]['id']
            
            # Process based on payment method
            if payment_method == 'cash':
                # For cash, process immediately
                return redirect(url_for('savings.process_cash_deposit', deposit_id=deposit_id))
            elif payment_method == 'pesapal':
                # For PesaPal, redirect to payment
                return redirect(url_for('savings.process_pesapal_deposit', deposit_id=deposit_id))
            else:
                flash('Deposit request created successfully', 'success')
                return redirect(url_for('savings.deposits'))
                
        except Exception as e:
            print(f"Error creating deposit: {e}")
            import traceback
            traceback.print_exc()
            flash('Error creating deposit request', 'error')
            return redirect(url_for('savings.new_deposit'))
    
    # GET request - show form
    try:
        # Get all savings accounts with member info
        accounts_res = supabase.table('savings_accounts')\
            .select('*, members(full_name, member_number)')\
            .eq('status', 'active')\
            .order('created_at', desc=True)\
            .execute()
        
        accounts = accounts_res.data if accounts_res.data else []
        
        return render_template('admin/savings/new_deposit.html', accounts=accounts)
        
    except Exception as e:
        print(f"Error loading deposit form: {e}")
        flash('Error loading deposit form', 'error')
        return redirect(url_for('savings.deposits'))

@savings_bp.route('/deposit/<deposit_id>/process-cash', methods=['GET', 'POST'])
@admin_login_required
def process_cash_deposit(deposit_id):
    """Process cash deposit"""
    try:
        # Get deposit request
        deposit_res = supabase.table('deposit_requests')\
            .select('*, savings_accounts(*)')\
            .eq('id', deposit_id)\
            .eq('status', 'processing')\
            .single()\
            .execute()
        
        if not deposit_res.data:
            return jsonify({'success': False, 'message': 'Deposit request not found or already processed'}), 400
        
        deposit = deposit_res.data
        account = deposit['savings_accounts']
        
        # Update deposit status
        supabase.table('deposit_requests')\
            .update({
                'status': 'completed',
                'confirmed_by': session.get('admin_id'),
                'confirmed_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', deposit_id)\
            .execute()
        
        # Update account balance
        new_balance = Decimal(str(account['current_balance'])) + Decimal(str(deposit['amount']))
        new_available = Decimal(str(account['available_balance'])) + Decimal(str(deposit['amount']))
        
        supabase.table('savings_accounts')\
            .update({
                'current_balance': float(new_balance),
                'available_balance': float(new_available),
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', account['id'])\
            .execute()
        
        # Create transaction record
        transaction_data = {
            'savings_account_id': account['id'],
            'member_id': account['member_id'],
            'transaction_type': 'deposit',
            'amount': deposit['amount'],
            'currency': 'UGX',
            'payment_method': 'cash',
            'reference_number': deposit['reference_number'],
            'description': deposit.get('description', 'Cash deposit'),
            'balance_before': float(account['current_balance']),
            'balance_after': float(new_balance),
            'processed_by': session.get('admin_id'),
            'status': 'completed',
            'created_at': datetime.now().isoformat()
        }
        
        supabase.table('savings_transactions').insert(transaction_data).execute()
        
        # Log activity
        log_savings_activity(account['id'], 'cash_deposit', 
                            f'Cash deposit of UGX {deposit["amount"]:,.0f} processed')
        
        return redirect(url_for('savings.account_details', account_id=account['id']))
        
    except Exception as e:
        print(f"Error processing cash deposit: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error processing cash deposit: {str(e)}'}), 500

@savings_bp.route('/deposit/<deposit_id>/process-pesapal')
@admin_login_required
def process_pesapal_deposit(deposit_id):
    """Initiate PesaPal payment for deposit"""
    try:
        # Get deposit request
        deposit_res = supabase.table('deposit_requests')\
            .select('*, savings_accounts(*, members(*))')\
            .eq('id', deposit_id)\
            .eq('status', 'pending')\
            .single()\
            .execute()
        
        if not deposit_res.data:
            flash('Deposit request not found or already processed', 'error')
            return redirect(url_for('savings.deposits'))
        
        deposit = deposit_res.data
        account = deposit['savings_accounts']
        member = account['members']
        
        # Initialize PesaPal
        pesapal = PesaPal()
        
        # Prepare payment details
        amount = float(deposit['amount'])
        reference_id = deposit['reference_number']
        
        # Extract names for billing
        names = member['full_name'].split()
        first_name = names[0] if names else "Member"
        last_name = names[-1] if len(names) > 1 else "User"
        
        # Get callback URL
        callback_url = url_for('savings.pesapal_deposit_callback', deposit_id=deposit_id, _external=True)
        
        # Submit order to PesaPal
        order = pesapal.submit_order(
            amount=amount,
            reference_id=reference_id,
            callback_url=callback_url,
            email=member['email'],
            first_name=first_name,
            last_name=last_name,
            description=f"Savings Deposit - {account['account_number']}"
        )
        
        if order and 'redirect_url' in order:
            # Update deposit with PesaPal info
            supabase.table('deposit_requests')\
                .update({
                    'pesapal_order_id': order['order_tracking_id'],
                    'pesapal_reference': reference_id,
                    'status': 'processing',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', deposit_id)\
                .execute()
            
            # Redirect to PesaPal
            return redirect(order['redirect_url'])
        else:
            flash('Failed to initiate PesaPal payment', 'error')
            return redirect(url_for('savings.deposits'))
            
    except Exception as e:
        print(f"Error initiating PesaPal deposit: {e}")
        flash('Error processing PesaPal deposit', 'error')
        return redirect(url_for('savings.deposits'))

@savings_bp.route('/deposit/<deposit_id>/pesapal-callback')
def pesapal_deposit_callback(deposit_id):
    """Handle PesaPal callback for deposit"""
    try:
        order_tracking_id = request.args.get('OrderTrackingId')
        
        if not order_tracking_id:
            flash('Invalid payment callback', 'error')
            return redirect(url_for('savings.deposits'))
        
        # Verify payment with PesaPal
        pesapal = PesaPal()
        payment_status = pesapal.verify_transaction_status(order_tracking_id)
        
        if not payment_status:
            flash('Could not verify payment status', 'error')
            return redirect(url_for('savings.deposits'))
        
        # Get deposit request
        deposit_res = supabase.table('deposit_requests')\
            .select('*, savings_accounts(*)')\
            .eq('id', deposit_id)\
            .single()\
            .execute()
        
        if not deposit_res.data:
            flash('Deposit request not found', 'error')
            return redirect(url_for('savings.deposits'))
        
        deposit = deposit_res.data
        account = deposit['savings_accounts']
        
        # Normalize payment status
        payment_status_desc = payment_status.get('payment_status_description', '').upper()
        if 'COMPLETED' in payment_status_desc:
            # Update deposit status
            supabase.table('deposit_requests')\
                .update({
                    'status': 'completed',
                    'pesapal_status': 'completed',
                    'pesapal_response': payment_status,
                    'confirmed_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', deposit_id)\
                .execute()
            
            # Update account balance
            new_balance = Decimal(str(account['current_balance'])) + Decimal(str(deposit['amount']))
            new_available = Decimal(str(account['available_balance'])) + Decimal(str(deposit['amount']))
            
            supabase.table('savings_accounts')\
                .update({
                    'current_balance': float(new_balance),
                    'available_balance': float(new_available),
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', account['id'])\
                .execute()
            
            # Create transaction record
            transaction_data = {
                'savings_account_id': account['id'],
                'member_id': account['member_id'],
                'transaction_type': 'deposit',
                'amount': deposit['amount'],
                'currency': 'UGX',
                'payment_method': 'pesapal',
                'reference_number': deposit['reference_number'],
                'pesapal_order_id': order_tracking_id,
                'description': deposit.get('description', 'PesaPal deposit'),
                'balance_before': float(account['current_balance']),
                'balance_after': float(new_balance),
                'status': 'completed',
                'created_at': datetime.now().isoformat()
            }
            
            supabase.table('savings_transactions').insert(transaction_data).execute()
            
            # Log activity
            log_savings_activity(account['id'], 'pesapal_deposit', 
                                f'PesaPal deposit of UGX {deposit["amount"]:,.0f} completed')
            
            flash('PesaPal deposit completed successfully', 'success')
            return redirect(url_for('savings.account_details', account_id=account['id']))
        
        elif 'PENDING' in payment_status_desc:
            flash('Payment is pending confirmation', 'info')
            return redirect(url_for('savings.deposits'))
        
        else:
            # Update deposit status to failed
            supabase.table('deposit_requests')\
                .update({
                    'status': 'failed',
                    'pesapal_status': 'failed',
                    'pesapal_response': payment_status,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', deposit_id)\
                .execute()
            
            flash('Payment failed. Please try again.', 'error')
            return redirect(url_for('savings.deposits'))
            
    except Exception as e:
        print(f"Error in PesaPal deposit callback: {e}")
        flash('Error processing payment callback', 'error')
        return redirect(url_for('savings.deposits'))

@savings_bp.route('/withdrawals')
@admin_login_required
def withdrawals():
    """View and manage withdrawal requests"""
    try:
        # Get filter parameters
        status = request.args.get('status', '')
        search = request.args.get('search', '')
        
        # Build query
        query = supabase.table('withdrawal_requests')\
            .select('*, savings_accounts(*, members(full_name, member_number))')\
            .order('created_at', desc=True)
        
        if status:
            query = query.eq('status', status)
        
        response = query.execute()
        withdrawals = response.data if response.data else []
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            filtered_withdrawals = []
            for withdrawal in withdrawals:
                account_info = withdrawal.get('savings_accounts', {})
                member_info = account_info.get('members', {})
                if (search_lower in withdrawal.get('reference_number', '').lower() or
                    search_lower in member_info.get('full_name', '').lower() or
                    search_lower in member_info.get('member_number', '').lower()):
                    filtered_withdrawals.append(withdrawal)
            withdrawals = filtered_withdrawals
        
        # Calculate statistics
        total_withdrawals = len(withdrawals)
        pending_withdrawals = len([w for w in withdrawals if w.get('status') == 'pending'])
        completed_withdrawals = len([w for w in withdrawals if w.get('status') == 'completed'])
        
        return render_template('admin/savings/withdrawals.html',
                             withdrawals=withdrawals,
                             status=status,
                             search=search,
                             total_withdrawals=total_withdrawals,
                             pending_withdrawals=pending_withdrawals,
                             completed_withdrawals=completed_withdrawals)
        
    except Exception as e:
        print(f"Error fetching withdrawals: {e}")
        flash('Error loading withdrawal requests', 'error')
        return render_template('admin/savings/withdrawals.html',
                             withdrawals=[],
                             status=status,
                             search=search,
                             total_withdrawals=0,
                             pending_withdrawals=0,
                             completed_withdrawals=0)

@savings_bp.route('/withdrawal/new', methods=['GET', 'POST'])
@admin_login_required
def new_withdrawal():
    """Create a new withdrawal request"""
    if request.method == 'POST':
        try:
            # Get form data
            savings_account_id = request.form.get('savings_account_id')
            amount = Decimal(request.form.get('amount', '0'))
            withdrawal_method = request.form.get('withdrawal_method', 'cash')
            description = request.form.get('description', '').strip()
            
            if not savings_account_id or amount <= 0:
                flash('Invalid withdrawal details', 'error')
                return redirect(url_for('savings.new_withdrawal'))
            
            # Get account details
            account_res = supabase.table('savings_accounts')\
                .select('*')\
                .eq('id', savings_account_id)\
                .single()\
                .execute()
            
            if not account_res.data:
                flash('Savings account not found', 'error')
                return redirect(url_for('savings.new_withdrawal'))
            
            account = account_res.data
            
            # Check available balance
            available_balance = Decimal(str(account['available_balance']))
            if amount > available_balance:
                flash(f'Insufficient funds. Available balance: UGX {available_balance:,.0f}', 'error')
                return redirect(url_for('savings.new_withdrawal'))
            
            # Create withdrawal request
            withdrawal_data = {
                'savings_account_id': savings_account_id,
                'member_id': account['member_id'],
                'amount': float(amount),
                'currency': 'UGX',
                'withdrawal_method': withdrawal_method,
                'description': description,
                'reference_number': f"WDL{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}",
                'status': 'pending',
                'requested_by': session.get('admin_id'),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Insert withdrawal request
            response = supabase.table('withdrawal_requests').insert(withdrawal_data).execute()
            
            if not response.data:
                flash('Failed to create withdrawal request', 'error')
                return redirect(url_for('savings.new_withdrawal'))
            
            flash('Withdrawal request created successfully', 'success')
            return redirect(url_for('savings.withdrawals'))
                
        except Exception as e:
            print(f"Error creating withdrawal: {e}")
            import traceback
            traceback.print_exc()
            flash('Error creating withdrawal request', 'error')
            return redirect(url_for('savings.new_withdrawal'))
    
    # GET request - show form
    try:
        # Get all savings accounts with member info
        accounts_res = supabase.table('savings_accounts')\
            .select('*, members(full_name, member_number)')\
            .eq('status', 'active')\
            .order('created_at', desc=True)\
            .execute()
        
        accounts = accounts_res.data if accounts_res.data else []
        
        return render_template('admin/savings/new_withdrawal.html', accounts=accounts)
        
    except Exception as e:
        print(f"Error loading withdrawal form: {e}")
        flash('Error loading withdrawal form', 'error')
        return redirect(url_for('savings.withdrawals'))

@savings_bp.route('/withdrawal/<withdrawal_id>/approve', methods=['POST'])
@admin_login_required
def approve_withdrawal(withdrawal_id):
    """Approve and process withdrawal request"""
    try:
        # Get withdrawal request
        withdrawal_res = supabase.table('withdrawal_requests')\
            .select('*, savings_accounts(*)')\
            .eq('id', withdrawal_id)\
            .eq('status', 'pending')\
            .single()\
            .execute()
        
        if not withdrawal_res.data:
            return jsonify({'success': False, 'message': 'Withdrawal request not found or already processed'}), 400
        
        withdrawal = withdrawal_res.data
        account = withdrawal['savings_accounts']
        
        # Check available balance
        available_balance = Decimal(str(account['available_balance']))
        withdrawal_amount = Decimal(str(withdrawal['amount']))
        
        if withdrawal_amount > available_balance:
            return jsonify({'success': False, 'message': f'Insufficient funds. Available: UGX {available_balance:,.0f}'}), 400
        
        # Update withdrawal status
        supabase.table('withdrawal_requests')\
            .update({
                'status': 'completed',
                'approved_by': session.get('admin_id'),
                'approved_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', withdrawal_id)\
            .execute()
        
        # Update account balance
        new_balance = Decimal(str(account['current_balance'])) - withdrawal_amount
        new_available = Decimal(str(account['available_balance'])) - withdrawal_amount
        
        supabase.table('savings_accounts')\
            .update({
                'current_balance': float(new_balance),
                'available_balance': float(new_available),
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', account['id'])\
            .execute()
        
        # Create transaction record
        transaction_data = {
            'savings_account_id': account['id'],
            'member_id': account['member_id'],
            'transaction_type': 'withdrawal',
            'amount': float(withdrawal_amount),
            'currency': 'UGX',
            'payment_method': withdrawal['withdrawal_method'],
            'reference_number': withdrawal['reference_number'],
            'description': withdrawal.get('description', 'Cash withdrawal'),
            'balance_before': float(account['current_balance']),
            'balance_after': float(new_balance),
            'processed_by': session.get('admin_id'),
            'status': 'completed',
            'created_at': datetime.now().isoformat()
        }
        
        supabase.table('savings_transactions').insert(transaction_data).execute()
        
        # Log activity
        log_savings_activity(account['id'], 'withdrawal_approved', 
                            f'Withdrawal of UGX {withdrawal_amount:,.0f} processed')
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal processed successfully',
            'new_balance': float(new_balance),
            'redirect_url': url_for('savings.account_details', account_id=account['id'])
        })
        
    except Exception as e:
        print(f"Error approving withdrawal: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error processing withdrawal: {str(e)}'}), 500

@savings_bp.route('/withdrawal/<withdrawal_id>/reject', methods=['POST'])
@admin_login_required
def reject_withdrawal(withdrawal_id):
    """Reject withdrawal request"""
    try:
        reason = request.form.get('reason', '').strip()
        
        if not reason:
            return jsonify({'success': False, 'message': 'Rejection reason is required'}), 400
        
        # Update withdrawal status
        supabase.table('withdrawal_requests')\
            .update({
                'status': 'rejected',
                'rejection_reason': reason,
                'rejected_by': session.get('admin_id'),
                'rejected_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', withdrawal_id)\
            .execute()
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal request rejected',
            'redirect_url': url_for('savings.withdrawals')
        })
        
    except Exception as e:
        print(f"Error rejecting withdrawal: {e}")
        return jsonify({'success': False, 'message': f'Error rejecting withdrawal: {str(e)}'}), 500

@savings_bp.route('/dashboard')
@admin_login_required
def dashboard():
    """Savings dashboard with statistics"""
    try:
        # Get total statistics
        accounts_res = supabase.table('savings_accounts')\
            .select('current_balance, available_balance, status')\
            .execute()
        
        accounts = accounts_res.data if accounts_res.data else []
        
        total_balance = sum(Decimal(str(acc['current_balance'])) for acc in accounts)
        total_available = sum(Decimal(str(acc['available_balance'])) for acc in accounts)
        active_accounts = len([acc for acc in accounts if acc['status'] == 'active'])
        
        # Get recent transactions
        transactions_res = supabase.table('savings_transactions')\
            .select('*, savings_accounts(account_number, members(full_name))')\
            .order('created_at', desc=True)\
            .limit(20)\
            .execute()
        
        recent_transactions = transactions_res.data if transactions_res.data else []
        
        # Get monthly deposits
        one_month_ago = (datetime.now() - timedelta(days=30)).isoformat()
        deposits_res = supabase.table('savings_transactions')\
            .select('amount')\
            .eq('transaction_type', 'deposit')\
            .eq('status', 'completed')\
            .gte('created_at', one_month_ago)\
            .execute()
        
        monthly_deposits = sum(Decimal(str(t['amount'])) for t in deposits_res.data) if deposits_res.data else 0
        
        # Get monthly withdrawals
        withdrawals_res = supabase.table('savings_transactions')\
            .select('amount')\
            .eq('transaction_type', 'withdrawal')\
            .eq('status', 'completed')\
            .gte('created_at', one_month_ago)\
            .execute()
        
        monthly_withdrawals = sum(Decimal(str(t['amount'])) for t in withdrawals_res.data) if withdrawals_res.data else 0
        
        # Get account growth (new accounts this month)
        new_accounts_res = supabase.table('savings_accounts')\
            .select('id')\
            .gte('created_at', one_month_ago)\
            .execute()
        
        new_accounts = len(new_accounts_res.data) if new_accounts_res.data else 0
        
        return render_template('admin/savings/dashboard.html',
                             total_balance=total_balance,
                             total_available=total_available,
                             active_accounts=active_accounts,
                             recent_transactions=recent_transactions,
                             monthly_deposits=monthly_deposits,
                             monthly_withdrawals=monthly_withdrawals,
                             new_accounts=new_accounts)
        
    except Exception as e:
        print(f"Error loading savings dashboard: {e}")
        flash('Error loading savings dashboard', 'error')
        return render_template('admin/savings/dashboard.html',
                             total_balance=0,
                             total_available=0,
                             active_accounts=0,
                             recent_transactions=[],
                             monthly_deposits=0,
                             monthly_withdrawals=0,
                             new_accounts=0)

# Utility functions
def log_savings_activity(account_id, action, description):
    """Log savings account activities"""
    try:
        supabase.table('savings_audit_log').insert({
            'savings_account_id': account_id,
            'action': action,
            'description': description,
            'performed_by': session.get('admin_id'),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'created_at': datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"Failed to log savings activity: {e}")

def calculate_savings_interest():
    """Calculate and apply interest to savings accounts"""
    try:
        # Get all active savings accounts
        accounts_res = supabase.table('savings_accounts')\
            .select('*')\
            .eq('status', 'active')\
            .execute()
        
        if not accounts_res.data:
            return 0
        
        accounts = accounts_res.data
        today = datetime.now()
        
        for account in accounts:
            # Check if interest was calculated this month
            last_calculated = account.get('last_interest_calculated')
            if last_calculated:
                last_date = datetime.fromisoformat(last_calculated.replace('Z', '+00:00'))
                if last_date.month == today.month and last_date.year == today.year:
                    continue  # Already calculated this month
            
            # Calculate monthly interest
            balance = Decimal(str(account['current_balance']))
            interest_rate = Decimal(str(account.get('interest_rate', 3.00))) / 100 / 12  # Monthly rate
            
            if balance > 0:
                interest = balance * interest_rate
                
                # Update account balance
                new_balance = balance + interest
                
                supabase.table('savings_accounts')\
                    .update({
                        'current_balance': float(new_balance),
                        'available_balance': float(new_balance),
                        'last_interest_calculated': today.isoformat(),
                        'updated_at': today.isoformat()
                    })\
                    .eq('id', account['id'])\
                    .execute()
                
                # Create interest transaction
                transaction_data = {
                    'savings_account_id': account['id'],
                    'member_id': account['member_id'],
                    'transaction_type': 'interest',
                    'amount': float(interest),
                    'currency': 'UGX',
                    'description': f'Monthly interest @ {account.get("interest_rate", 3.00)}% p.a.',
                    'balance_before': float(balance),
                    'balance_after': float(new_balance),
                    'status': 'completed',
                    'created_at': today.isoformat()
                }
                
                supabase.table('savings_transactions').insert(transaction_data).execute()
                
                # Log activity
                log_savings_activity(account['id'], 'interest_calculated', 
                                    f'Interest of UGX {interest:,.2f} applied')
        
        return len(accounts)
        
    except Exception as e:
        print(f"Error calculating interest: {e}")
        import traceback
        traceback.print_exc()
        return 0

# Scheduled task to calculate interest
@savings_bp.route('/calculate-interest')
def calculate_interest_endpoint():
    """Endpoint to manually trigger interest calculation"""
    try:
        if 'admin_logged_in' not in session:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
        accounts_processed = calculate_savings_interest()
        return jsonify({
            'success': True,
            'message': f'Interest calculated for {accounts_processed} accounts.'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500