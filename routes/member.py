import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from supabase import create_client, Client
from datetime import datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv
from pesapal import PesaPal
import uuid
from io import BytesIO
from xhtml2pdf import pisa
from flask import Response
import base64


load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Create Blueprint
member_bp = Blueprint('member', __name__, url_prefix='/member')

# Member login required decorator
def member_login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'member_logged_in' not in session or not session.get('member_logged_in'):
            flash('Please login to access this page', 'error')
            return redirect(url_for('memberauth.member_login'))
        return f(*args, **kwargs)
    return decorated_function


def generate_statement_pdf(data):
    """Generate PDF from HTML template"""
    try:
        # Ensure all required keys exist
        data.setdefault('member', {})
        data.setdefault('savings_account', {})
        data.setdefault('loan_account', {})
        data.setdefault('savings_transactions', [])
        data.setdefault('loan_transactions', [])
        data.setdefault('repayments', [])
        data.setdefault('total_deposits', 0)
        data.setdefault('total_withdrawals', 0)
        data.setdefault('total_repayments', 0)
        data.setdefault('total_disbursements', 0)
        
        # Render HTML template
        html = render_template('member/statement_pdf.html', **data)
        
        # Create PDF
        pdf = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf)
        
        if pisa_status.err:
            raise Exception(f"PDF generation error: {pisa_status.err}")
        
        pdf.seek(0)
        return pdf.getvalue()
        
    except Exception as e:
        print(f"Error in PDF generation: {e}")
        raise
    
    
    
# Routes
@member_bp.route('/')
@member_login_required
def dashboard():
    """Member dashboard"""
    try:
        member_id = session['member_id']
        print(f"DEBUG: Loading dashboard for member_id: {member_id}")
        
        # Get member details
        member_res = supabase.table('members')\
            .select('*')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data
        print(f"DEBUG: Member data: {member}")
        
        # Get savings account - with default values
        try:
            savings_res = supabase.table('savings_accounts')\
                .select('*')\
                .eq('member_id', member_id)\
                .single()\
                .execute()
            
            savings_account = savings_res.data
            print(f"DEBUG: Savings account found: {savings_account}")
        except Exception as e:
            print(f"DEBUG: No savings account found or error: {e}")
            # Provide default values
            savings_account = {
                'current_balance': 0,
                'available_balance': 0,
                'account_number': 'Not assigned'
            }
        
        # Get loan account - with default values
        try:
            loan_res = supabase.table('loan_accounts')\
                .select('*')\
                .eq('member_id', member_id)\
                .single()\
                .execute()
            
            loan_account = loan_res.data
            print(f"DEBUG: Loan account found: {loan_account}")
        except Exception as e:
            print(f"DEBUG: No loan account found or error: {e}")
            # Provide default values
            loan_account = {
                'current_balance': 0,
                'available_limit': 0,
                'account_number': 'Not assigned'
            }
        
        # Get recent transactions
        transactions_res = supabase.table('savings_transactions')\
            .select('*')\
            .eq('member_id', member_id)\
            .order('created_at', desc=True)\
            .limit(10)\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        print(f"DEBUG: Found {len(transactions)} transactions")
        
        # Get loan applications
        loan_apps_res = supabase.table('loan_applications')\
            .select('*')\
            .eq('member_id', member_id)\
            .order('created_at', desc=True)\
            .limit(5)\
            .execute()
        
        loan_applications = loan_apps_res.data if loan_apps_res.data else []
        print(f"DEBUG: Found {len(loan_applications)} loan applications")
        
        # Get pending repayments
        repayments_res = supabase.table('loan_repayments')\
            .select('*')\
            .eq('member_id', member_id)\
            .eq('status', 'pending')\
            .order('due_date')\
            .execute()
        
        pending_repayments = repayments_res.data if repayments_res.data else []
        print(f"DEBUG: Found {len(pending_repayments)} pending repayments")
        
        # Get current share value
        try:
            share_value_res = supabase.table('share_value')\
                .select('value_per_share')\
                .order('effective_date', desc=True)\
                .limit(1)\
                .single()\
                .execute()
            
            share_value = share_value_res.data['value_per_share'] if share_value_res.data else 1000
        except Exception as e:
            print(f"DEBUG: Error getting share value: {e}")
            share_value = 1000
        
        print(f"DEBUG: Current share value: {share_value}")
        print(f"DEBUG: Savings account current_balance: {savings_account.get('current_balance', 'Not found')}")
        print(f"DEBUG: Loan account current_balance: {loan_account.get('current_balance', 'Not found')}")
        
        return render_template('member/dashboard.html',
                             member=member,
                             savings_account=savings_account,
                             loan_account=loan_account,
                             transactions=transactions,
                             loan_applications=loan_applications,
                             pending_repayments=pending_repayments,
                             share_value=share_value)
        
    except Exception as e:
        print(f"Error loading dashboard: {e}")
        flash('Error loading dashboard', 'error')
        # Provide default values when there's an error
        return render_template('member/dashboard.html',
                             member={'full_name': session.get('member_name', 'Member'),
                                     'member_number': session.get('member_number', ''),
                                     'email': session.get('member_email', ''),
                                     'account_status': 'active',
                                     'shares_owned': 0,
                                     'created_at': '',
                                     'phone_number': '',
                                     'updated_at': ''},
                             savings_account={'current_balance': 0, 'available_balance': 0, 'account_number': 'N/A'},
                             loan_account={'current_balance': 0, 'available_limit': 0, 'account_number': 'N/A'},
                             transactions=[],
                             loan_applications=[],
                             pending_repayments=[],
                             share_value=1000)
        
@member_bp.route('/update-profile', methods=['POST'])
@member_login_required
def update_profile():
    """Update member profile"""
    try:
        member_id = session['member_id']
        
        # Get form data
        update_data = {
            'phone_number': request.form.get('phone_number', '').strip(),
            'contact_address': request.form.get('contact_address', '').strip(),
            'emergency_contact_name': request.form.get('emergency_contact_name', '').strip(),
            'emergency_contact_phone': request.form.get('emergency_contact_phone', '').strip(),
            'emergency_contact_relationship': request.form.get('emergency_contact_relationship', '').strip(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Update member
        supabase.table('members')\
            .update(update_data)\
            .eq('id', member_id)\
            .execute()
        
        flash('Profile updated successfully', 'success')
        return redirect(url_for('member.profile'))
        
    except Exception as e:
        print(f"Error updating profile: {e}")
        flash('Error updating profile', 'error')
        return redirect(url_for('member.profile'))

@member_bp.route('/savings')
@member_login_required
def savings():
    """Savings account details"""
    try:
        member_id = session['member_id']
        
        # Get member details for PesaPal payment
        member_res = supabase.table('members')\
            .select('*')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data
        
        # Get savings account
        savings_res = supabase.table('savings_accounts')\
            .select('*')\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        savings_account = savings_res.data if savings_res.data else None
        
        # Get transactions
        transactions_res = supabase.table('savings_transactions')\
            .select('*')\
            .eq('member_id', member_id)\
            .order('created_at', desc=True)\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        
        # Get recent deposits for quick deposit amounts
        recent_deposits = [t for t in transactions[:5] if t.get('transaction_type') == 'deposit']
        
        return render_template('member/savings.html',
                             member=member,
                             savings_account=savings_account,
                             transactions=transactions,
                             recent_deposits=recent_deposits)
        
    except Exception as e:
        print(f"Error loading savings: {e}")
        flash('Error loading savings information', 'error')
        return render_template('member/savings.html')
    
@member_bp.route('/initiate-deposit', methods=['POST'])
@member_login_required
def initiate_deposit():
    """Initiate a deposit via PesaPal"""
    try:
        member_id = session['member_id']
        amount = Decimal(request.form.get('amount', '0'))
        
        if amount <= 0:
            flash('Please enter a valid amount', 'error')
            return redirect(url_for('member.savings'))
        
        # Get member details
        member_res = supabase.table('members')\
            .select('full_name, email, phone_number')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data
        
        # Get savings account
        savings_res = supabase.table('savings_accounts')\
            .select('id, account_number, current_balance, available_balance')\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        savings_account = savings_res.data
        
        # Create a transaction record with correct schema
        transaction_id = str(uuid.uuid4())
        transaction_data = {
            'id': transaction_id,
            'savings_account_id': savings_account['id'],
            'member_id': member_id,
            'transaction_type': 'deposit',
            'amount': str(amount),
            'description': f'Online deposit to savings account',
            'reference_number': f'DEP-{transaction_id[:8].upper()}',
            'balance_before': str(savings_account['current_balance']),
            'balance_after': str(Decimal(savings_account['current_balance']) + amount),
            'status': 'pending',
            'payment_method': 'pesapal',
            'currency': 'UGX',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('savings_transactions').insert(transaction_data).execute()
        
        # Initialize PesaPal
        pesapal = PesaPal()
        
        # Prepare payment details
        reference_id = f"SAV-{transaction_id[:8].upper()}"
        
        # Extract names for billing
        names = member['full_name'].split()
        first_name = names[0] if names else "Member"
        last_name = names[-1] if len(names) > 1 else "User"
        
        # Get callback URL
        callback_url = url_for('member.deposit_callback', _external=True)
        
        # Submit order to PesaPal
        order = pesapal.submit_order(
            amount=float(amount),
            reference_id=reference_id,
            callback_url=callback_url,
            email=member['email'],
            first_name=first_name,
            last_name=last_name
        )
        
        if order and order.get('redirect_url'):
            # Update transaction with PesaPal order ID
            supabase.table('savings_transactions')\
                .update({
                    'pesapal_order_id': order['order_tracking_id'],
                    'reference_number': reference_id
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # Store in payment sessions for callback
            payment_session_data = {
                'transaction_id': transaction_id,
                'member_id': member_id,
                'savings_account_id': savings_account['id'],
                'order_tracking_id': order['order_tracking_id'],
                'reference_id': reference_id,
                'amount': str(amount),
                'balance_before': str(savings_account['current_balance']),
                'created_at': datetime.now().isoformat()
            }
            
            supabase.table('savings_payment_sessions').insert(payment_session_data).execute()
            
            # Redirect to PesaPal
            return redirect(order['redirect_url'])
        else:
            # Update transaction as failed
            supabase.table('savings_transactions')\
                .update({'status': 'failed'})\
                .eq('id', transaction_id)\
                .execute()
            
            flash('Failed to initiate payment. Please try again.', 'error')
            return redirect(url_for('member.savings'))
            
    except Exception as e:
        print(f"Error initiating deposit: {e}")
        flash('Error initiating deposit', 'error')
        return redirect(url_for('member.savings'))

@member_bp.route('/deposit-callback', methods=['GET'])
@member_login_required
def deposit_callback():
    """Handle PesaPal callback for deposit"""
    try:
        order_tracking_id = request.args.get('OrderTrackingId')
        merchant_reference = request.args.get('OrderMerchantReference')  # Get merchant reference
        
        if not order_tracking_id:
            flash('Invalid payment callback', 'error')
            return redirect(url_for('member.savings'))
        
        # Get payment session
        payment_session_res = supabase.table('savings_payment_sessions')\
            .select('*')\
            .eq('order_tracking_id', order_tracking_id)\
            .single()\
            .execute()
        
        if not payment_session_res.data:
            flash('Payment session not found', 'error')
            return redirect(url_for('member.savings'))
        
        payment_session = payment_session_res.data
        transaction_id = payment_session['transaction_id']
        member_id = payment_session['member_id']
        savings_account_id = payment_session['savings_account_id']
        amount = Decimal(payment_session['amount'])
        balance_before = Decimal(payment_session['balance_before'])
        original_reference = payment_session['reference_id']
        
        # Verify payment with PesaPal
        pesapal = PesaPal()
        payment_status = pesapal.verify_transaction_status(order_tracking_id)
        
        if not payment_status:
            flash('Could not verify payment status', 'error')
            return redirect(url_for('member.savings'))
        
        # Normalize payment status
        payment_status_desc = payment_status.get('payment_status_description', '').upper()
        if 'COMPLETED' in payment_status_desc:
            normalized_status = 'completed'
        elif 'PENDING' in payment_status_desc:
            normalized_status = 'pending'
        else:
            normalized_status = 'failed'
        
        if normalized_status == 'completed':
            # Check if transaction already exists to avoid duplicates
            existing_transaction_res = supabase.table('savings_transactions')\
                .select('*')\
                .eq('reference_number', original_reference)\
                .eq('status', 'completed')\
                .execute()
            
            if existing_transaction_res.data:
                # Transaction already processed
                flash(f'Deposit of UGX {amount:,.0f} was already processed successfully!', 'info')
                return redirect(url_for('member.savings'))
            
            # Update savings account balance
            savings_res = supabase.table('savings_accounts')\
                .select('current_balance, available_balance')\
                .eq('id', savings_account_id)\
                .single()\
                .execute()
            
            savings_account = savings_res.data
            new_balance = Decimal(savings_account['current_balance']) + amount
            new_available = Decimal(savings_account['available_balance']) + amount
            
            # Update account balances
            supabase.table('savings_accounts')\
                .update({
                    'current_balance': str(new_balance),
                    'available_balance': str(new_available),
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', savings_account_id)\
                .execute()
            
            # Update the original pending transaction to completed
            supabase.table('savings_transactions')\
                .update({
                    'status': 'completed',
                    'balance_before': str(balance_before),
                    'balance_after': str(new_balance),
                    'pesapal_order_id': order_tracking_id,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # If merchant_reference is different, update it
            if merchant_reference and merchant_reference != original_reference:
                try:
                    supabase.table('savings_transactions')\
                        .update({
                            'reference_number': merchant_reference
                        })\
                        .eq('id', transaction_id)\
                        .execute()
                except Exception as e:
                    print(f"Note: Could not update reference number: {e}")
                    # It's okay if we can't update, keep the original
            
            # Clear payment session
            supabase.table('savings_payment_sessions')\
                .delete()\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            flash(f'Deposit of UGX {amount:,.0f} completed successfully!', 'success')
            
        elif normalized_status == 'pending':
            # Update transaction status
            supabase.table('savings_transactions')\
                .update({
                    'status': 'pending',
                    'pesapal_order_id': order_tracking_id,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', transaction_id)\
                .execute()
            
            flash('Payment is pending confirmation. Your account will be updated once payment is confirmed.', 'info')
        
        else:
            # Update transaction as failed
            supabase.table('savings_transactions')\
                .update({
                    'status': 'failed',
                    'pesapal_order_id': order_tracking_id,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', transaction_id)\
                .execute()
            
            flash('Payment failed. Please try again.', 'error')
        
        return redirect(url_for('member.savings'))
            
    except Exception as e:
        print(f"Error in deposit callback: {e}")
        flash('Error processing payment callback', 'error')
        return redirect(url_for('member.savings'))
    
@member_bp.route('/quick-deposit', methods=['POST'])
@member_login_required
def quick_deposit():
    """Handle quick deposit with predefined amounts"""
    try:
        amount = Decimal(request.form.get('amount', '0'))
        
        if amount <= 0:
            flash('Please select a valid amount', 'error')
            return redirect(url_for('member.savings'))
        
        # Call the initiate_deposit function with the amount
        # We'll use a session to pass the amount
        session['deposit_amount'] = str(amount)
        
        # Create a form data dict for the initiate_deposit endpoint
        class FormData:
            def __init__(self, data):
                self.data = data
            
            def get(self, key, default=None):
                return self.data.get(key, default)
        
        # Simulate form submission
        request.form = FormData({'amount': str(amount)})
        
        return initiate_deposit()
        
    except Exception as e:
        print(f"Error in quick deposit: {e}")
        flash('Error processing quick deposit', 'error')
        return redirect(url_for('member.savings'))
    
    
    
@member_bp.route('/loans')
@member_login_required
def loans():
    """Loan account details"""
    try:
        member_id = session['member_id']
        
        # Get loan account
        loan_res = supabase.table('loan_accounts')\
            .select('*')\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        loan_account = loan_res.data if loan_res.data else None
        
        # Get loan applications
        apps_res = supabase.table('loan_applications')\
            .select('*, loan_products(name, interest_rate)')\
            .eq('member_id', member_id)\
            .order('created_at', desc=True)\
            .execute()
        
        applications = apps_res.data if apps_res.data else []
        
        # Get repayments with loan application details
        repayments_res = supabase.table('loan_repayments')\
            .select('*, loan_applications(loan_amount, account_number, purpose)')\
            .eq('member_id', member_id)\
            .order('due_date')\
            .execute()
        
        repayments = repayments_res.data if repayments_res.data else []
        
        # Get loan products for new application
        products_res = supabase.table('loan_products')\
            .select('*')\
            .eq('status', 'active')\
            .execute()
        
        products = products_res.data if products_res.data else []
        
        # Get loan transactions
        transactions_res = supabase.table('loan_transactions')\
            .select('*')\
            .eq('loan_account_id', loan_account['id'] if loan_account else None)\
            .order('created_at', desc=True)\
            .limit(10)\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        
        return render_template('member/loans.html',
                             loan_account=loan_account,
                             applications=applications,
                             repayments=repayments,
                             products=products,
                             transactions=transactions)
        
    except Exception as e:
        print(f"Error loading loans: {e}")
        flash('Error loading loan information', 'error')
        return render_template('member/loans.html')

@member_bp.route('/pay-repayment', methods=['POST'])
@member_login_required
def pay_repayment():
    """Pay a specific repayment installment via PesaPal"""
    try:
        member_id = session['member_id']
        repayment_id = request.form.get('repayment_id')
        custom_amount = Decimal(request.form.get('custom_amount', '0'))
        
        if not repayment_id:
            flash('Repayment ID is required', 'error')
            return redirect(url_for('member.loans'))
        
        # Get repayment details
        repayment_res = supabase.table('loan_repayments')\
            .select('*, loan_applications(loan_amount, account_number)')\
            .eq('id', repayment_id)\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        if not repayment_res.data:
            flash('Repayment not found', 'error')
            return redirect(url_for('member.loans'))
        
        repayment = repayment_res.data
        loan_application = repayment.get('loan_applications', {})
        
        # Calculate amount to pay
        if custom_amount > 0:
            amount = custom_amount
            payment_type = 'partial'
        else:
            amount = Decimal(repayment['due_amount']) - Decimal(repayment.get('paid_amount', '0'))
            payment_type = 'full'
        
        if amount <= 0:
            flash('No amount due for this repayment', 'info')
            return redirect(url_for('member.loans'))
        
        # Get member details
        member_res = supabase.table('members')\
            .select('full_name, email, phone_number')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data
        
        # Get loan account for reference
        loan_res = supabase.table('loan_accounts')\
            .select('id, account_number, current_balance')\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        loan_account = loan_res.data
        
        # Create transaction record WITHOUT status
        transaction_id = str(uuid.uuid4())
        transaction_data = {
            'id': transaction_id,
            'loan_account_id': loan_account['id'],
            'loan_application_id': repayment['loan_application_id'],
            'transaction_type': 'repayment',
            'amount': str(amount),
            'balance_before': str(loan_account['current_balance']),
            'balance_after': str(Decimal(loan_account['current_balance']) - amount),
            'payment_method': 'pesapal',
            'reference_number': f'REP-{transaction_id[:8].upper()}',
            'description': f'Repayment for installment {repayment["installment_number"]}',
            'created_at': datetime.now().isoformat()
        }
        
        supabase.table('loan_transactions').insert(transaction_data).execute()
        
        # Initialize PesaPal
        pesapal = PesaPal()
        
        # Prepare payment details
        reference_id = f"LOAN-REP-{transaction_id[:8].upper()}"
        
        # Extract names for billing
        names = member['full_name'].split()
        first_name = names[0] if names else "Member"
        last_name = names[-1] if len(names) > 1 else "User"
        
        # Get callback URL
        callback_url = url_for('member.repayment_callback', _external=True)
        
        # Submit order to PesaPal
        order = pesapal.submit_order(
            amount=float(amount),
            reference_id=reference_id,
            callback_url=callback_url,
            email=member['email'],
            first_name=first_name,
            last_name=last_name
        )
        
        if order and order.get('redirect_url'):
            # Update transaction with PesaPal order ID
            supabase.table('loan_transactions')\
                .update({
                    'reference_number': reference_id,
                    'payment_method': 'pesapal_pending'
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # Store in payment sessions for callback
            payment_session_data = {
                'transaction_id': transaction_id,
                'member_id': member_id,
                'repayment_id': repayment_id,
                'loan_account_id': loan_account['id'],
                'loan_application_id': repayment['loan_application_id'],
                'order_tracking_id': order['order_tracking_id'],
                'reference_id': reference_id,
                'amount': str(amount),
                'balance_before': str(loan_account['current_balance']),
                'payment_type': payment_type,
                'installment_number': repayment['installment_number'],
                'status': 'pending',
                'created_at': datetime.now().isoformat()
            }
            
            supabase.table('loan_payment_sessions').insert(payment_session_data).execute()
            
            # Redirect to PesaPal
            return redirect(order['redirect_url'])
        else:
            # Update transaction as failed
            supabase.table('loan_transactions')\
                .update({
                    'payment_method': 'pesapal_failed'
                })\
                .eq('id', transaction_id)\
                .execute()
            
            flash('Failed to initiate payment. Please try again.', 'error')
            return redirect(url_for('member.loans'))
            
    except Exception as e:
        print(f"Error initiating repayment payment: {e}")
        flash('Error initiating payment', 'error')
        return redirect(url_for('member.loans'))

@member_bp.route('/repayment-callback', methods=['GET'])
@member_login_required
def repayment_callback():
    """Handle PesaPal callback for loan repayment"""
    try:
        order_tracking_id = request.args.get('OrderTrackingId')
        merchant_reference = request.args.get('OrderMerchantReference')
        
        if not order_tracking_id:
            flash('Invalid payment callback', 'error')
            return redirect(url_for('member.loans'))
        
        # Get payment session
        payment_session_res = supabase.table('loan_payment_sessions')\
            .select('*')\
            .eq('order_tracking_id', order_tracking_id)\
            .single()\
            .execute()
        
        if not payment_session_res.data:
            flash('Payment session not found', 'error')
            return redirect(url_for('member.loans'))
        
        payment_session = payment_session_res.data
        transaction_id = payment_session['transaction_id']
        member_id = payment_session['member_id']
        repayment_id = payment_session['repayment_id']
        loan_account_id = payment_session['loan_account_id']
        loan_application_id = payment_session['loan_application_id']
        amount = Decimal(payment_session['amount'])
        balance_before = Decimal(payment_session['balance_before'])
        payment_type = payment_session['payment_type']
        installment_number = payment_session['installment_number']
        
        # Verify payment with PesaPal
        pesapal = PesaPal()
        payment_status = pesapal.verify_transaction_status(order_tracking_id)
        
        if not payment_status:
            flash('Could not verify payment status', 'error')
            return redirect(url_for('member.loans'))
        
        # Normalize payment status
        payment_status_desc = payment_status.get('payment_status_description', '').upper()
        if 'COMPLETED' in payment_status_desc:
            normalized_status = 'completed'
        elif 'PENDING' in payment_status_desc:
            normalized_status = 'pending'
        else:
            normalized_status = 'failed'
        
        if normalized_status == 'completed':
            # Check if transaction already processed by looking at payment_method
            existing_transaction_res = supabase.table('loan_transactions')\
                .select('*')\
                .eq('id', transaction_id)\
                .execute()
            
            existing_transaction = existing_transaction_res.data[0] if existing_transaction_res.data else None
            
            if existing_transaction and existing_transaction.get('payment_method') == 'pesapal_completed':
                flash(f'Payment of UGX {amount:,.0f} was already processed!', 'info')
                return redirect(url_for('member.loans'))
            
            # Update loan account balance
            loan_res = supabase.table('loan_accounts')\
                .select('current_balance, available_limit')\
                .eq('id', loan_account_id)\
                .single()\
                .execute()
            
            loan_account = loan_res.data
            new_balance = Decimal(loan_account['current_balance']) - amount
            new_available = Decimal(loan_account['available_limit']) + amount
            
            # Update account balances
            supabase.table('loan_accounts')\
                .update({
                    'current_balance': str(new_balance),
                    'available_limit': str(new_available),
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', loan_account_id)\
                .execute()
            
            # Update the transaction using payment_method
            supabase.table('loan_transactions')\
                .update({
                    'balance_before': str(balance_before),
                    'balance_after': str(new_balance),
                    'payment_method': 'pesapal_completed',
                    'reference_number': merchant_reference or payment_session['reference_id'],
                    'description': f'Repayment for installment #{installment_number} completed via PesaPal'
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # Update repayment record
            repayment_res = supabase.table('loan_repayments')\
                .select('paid_amount, due_amount')\
                .eq('id', repayment_id)\
                .single()\
                .execute()
            
            repayment = repayment_res.data
            current_paid = Decimal(repayment['paid_amount'])
            new_paid = current_paid + amount
            due_amount = Decimal(repayment['due_amount'])
            
            # Determine new status
            if new_paid >= due_amount:
                new_status = 'paid'
            elif new_paid > 0:
                new_status = 'partial'
            else:
                new_status = 'pending'
            
            supabase.table('loan_repayments')\
                .update({
                    'paid_amount': str(new_paid),
                    'paid_date': datetime.now().date().isoformat(),
                    'payment_method': 'pesapal',
                    'reference_number': merchant_reference or payment_session['reference_id'],
                    'status': new_status,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', repayment_id)\
                .execute()
            
            # Update payment session
            supabase.table('loan_payment_sessions')\
                .update({
                    'status': 'completed',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            flash(f'Payment of UGX {amount:,.0f} for installment #{installment_number} completed successfully!', 'success')
            
        elif normalized_status == 'pending':
            # Update transaction using payment_method
            supabase.table('loan_transactions')\
                .update({
                    'payment_method': 'pesapal_pending',
                    'description': f'Repayment for installment #{installment_number} pending via PesaPal'
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # Update payment session
            supabase.table('loan_payment_sessions')\
                .update({
                    'status': 'pending',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            flash('Payment is pending confirmation. Your account will be updated once payment is confirmed.', 'info')
        
        else:
            # Update transaction as failed using payment_method
            supabase.table('loan_transactions')\
                .update({
                    'payment_method': 'pesapal_failed',
                    'description': f'Repayment for installment #{installment_number} failed via PesaPal'
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # Update payment session
            supabase.table('loan_payment_sessions')\
                .update({
                    'status': 'failed',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            flash('Payment failed. Please try again.', 'error')
        
        return redirect(url_for('member.loans'))
            
    except Exception as e:
        print(f"Error in repayment callback: {e}")
        flash('Error processing payment callback', 'error')
        return redirect(url_for('member.loans'))


@member_bp.route('/apply-loan', methods=['POST'])
@member_login_required
def apply_loan():
    """Apply for a loan"""
    try:
        member_id = session['member_id']
        
        # Get form data
        loan_product_id = request.form.get('loan_product_id')
        loan_amount = Decimal(request.form.get('loan_amount', '0'))
        purpose = request.form.get('purpose', '').strip()
        repayment_period = int(request.form.get('repayment_period', '12'))
        
        # Validate
        if loan_amount <= 0:
            flash('Invalid loan amount', 'error')
            return redirect(url_for('member.loans'))
        
        # Get member details
        member_res = supabase.table('members')\
            .select('member_number')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data
        
        # Get loan product
        product_res = supabase.table('loan_products')\
            .select('*')\
            .eq('id', loan_product_id)\
            .single()\
            .execute()
        
        product = product_res.data if product_res.data else None
        
        if not product:
            flash('Invalid loan product', 'error')
            return redirect(url_for('member.loans'))
        
        # Check if amount is within product limits
        if loan_amount < Decimal(product['min_amount']) or loan_amount > Decimal(product['max_amount']):
            flash(f'Loan amount must be between UGX {product["min_amount"]:,.0f} and UGX {product["max_amount"]:,.0f}', 'error')
            return redirect(url_for('member.loans'))
        
        # Get loan account for account number
        loan_account_res = supabase.table('loan_accounts')\
            .select('account_number')\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        loan_account = loan_account_res.data if loan_account_res.data else None
        
        # Calculate monthly installment (simple calculation)
        interest_rate = Decimal(product['interest_rate'])
        monthly_interest = interest_rate / 12 / 100
        monthly_payment = (loan_amount * monthly_interest) / (1 - (1 + monthly_interest) ** -repayment_period)
        total_repayable = monthly_payment * repayment_period
        
        # Create loan application
        application_data = {
            'member_id': member_id,
            'loan_product_id': loan_product_id,
            'account_number': loan_account['account_number'] if loan_account else f"LA{member['member_number']}",
            'loan_amount': str(loan_amount),
            'purpose': purpose,
            'repayment_period_months': repayment_period,
            'interest_rate': str(interest_rate),
            'monthly_installment': str(monthly_payment),
            'total_repayable': str(total_repayable),
            'net_disbursement': str(loan_amount),  # Assuming no fees for now
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('loan_applications').insert(application_data).execute()
        
        flash('Loan application submitted successfully. It will be reviewed by an admin.', 'success')
        return redirect(url_for('member.loans'))
        
    except Exception as e:
        print(f"Error applying for loan: {e}")
        flash('Error submitting loan application', 'error')
        return redirect(url_for('member.loans'))
    
    
@member_bp.route('/pay-total-balance', methods=['POST'])
@member_login_required
def pay_total_balance():
    """Pay the total loan balance via PesaPal"""
    try:
        member_id = session['member_id']
        amount = Decimal(request.form.get('amount', '0'))
        
        if amount <= 0:
            flash('Please enter a valid amount', 'error')
            return redirect(url_for('member.loans'))
        
        # Get loan account details
        loan_res = supabase.table('loan_accounts')\
            .select('id, account_number, current_balance')\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        if not loan_res.data:
            flash('Loan account not found', 'error')
            return redirect(url_for('member.loans'))
        
        loan_account = loan_res.data
        
        # Check if amount exceeds balance
        if amount > Decimal(loan_account['current_balance']):
            flash(f'Amount exceeds current balance of UGX {Decimal(loan_account["current_balance"]):,.0f}', 'error')
            return redirect(url_for('member.loans'))
        
        # Get member details
        member_res = supabase.table('members')\
            .select('full_name, email, phone_number')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data
        
        # Create transaction record WITHOUT status column
        transaction_id = str(uuid.uuid4())
        transaction_data = {
            'id': transaction_id,
            'loan_account_id': loan_account['id'],
            'transaction_type': 'repayment',
            'amount': str(amount),
            'balance_before': str(loan_account['current_balance']),
            'balance_after': str(Decimal(loan_account['current_balance']) - amount),
            'payment_method': 'pesapal',
            'reference_number': f'BAL-{transaction_id[:8].upper()}',
            'description': f'Full/partial loan balance payment',
            'created_at': datetime.now().isoformat()
        }
        
        supabase.table('loan_transactions').insert(transaction_data).execute()
        
        # Initialize PesaPal
        pesapal = PesaPal()
        
        # Prepare payment details
        reference_id = f"LOAN-BAL-{transaction_id[:8].upper()}"
        
        # Extract names for billing
        names = member['full_name'].split()
        first_name = names[0] if names else "Member"
        last_name = names[-1] if len(names) > 1 else "User"
        
        # Get callback URL
        callback_url = url_for('member.balance_callback', _external=True)
        
        # Submit order to PesaPal
        order = pesapal.submit_order(
            amount=float(amount),
            reference_id=reference_id,
            callback_url=callback_url,
            email=member['email'],
            first_name=first_name,
            last_name=last_name
        )
        
        if order and order.get('redirect_url'):
            # Update transaction with PesaPal order ID
            supabase.table('loan_transactions')\
                .update({
                    'reference_number': reference_id,
                    'payment_method': 'pesapal_pending'  # Use payment_method to track status
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # Store in payment sessions
            payment_session_data = {
                'transaction_id': transaction_id,
                'member_id': member_id,
                'loan_account_id': loan_account['id'],
                'order_tracking_id': order['order_tracking_id'],
                'reference_id': reference_id,
                'amount': str(amount),
                'balance_before': str(loan_account['current_balance']),
                'payment_type': 'balance',
                'status': 'pending',  # Status stored in payment session
                'created_at': datetime.now().isoformat()
            }
            
            supabase.table('loan_payment_sessions').insert(payment_session_data).execute()
            
            # Redirect to PesaPal
            return redirect(order['redirect_url'])
        else:
            # Update transaction as failed (using payment_method field)
            supabase.table('loan_transactions')\
                .update({
                    'payment_method': 'pesapal_failed'
                })\
                .eq('id', transaction_id)\
                .execute()
            
            flash('Failed to initiate payment. Please try again.', 'error')
            return redirect(url_for('member.loans'))
            
    except Exception as e:
        print(f"Error initiating balance payment: {e}")
        flash('Error initiating payment', 'error')
        return redirect(url_for('member.loans'))
    
@member_bp.route('/balance-callback', methods=['GET'])
@member_login_required
def balance_callback():
    """Handle PesaPal callback for loan balance payment"""
    try:
        order_tracking_id = request.args.get('OrderTrackingId')
        merchant_reference = request.args.get('OrderMerchantReference')
        
        if not order_tracking_id:
            flash('Invalid payment callback', 'error')
            return redirect(url_for('member.loans'))
        
        # Get payment session
        payment_session_res = supabase.table('loan_payment_sessions')\
            .select('*')\
            .eq('order_tracking_id', order_tracking_id)\
            .single()\
            .execute()
        
        if not payment_session_res.data:
            flash('Payment session not found', 'error')
            return redirect(url_for('member.loans'))
        
        payment_session = payment_session_res.data
        transaction_id = payment_session['transaction_id']
        member_id = payment_session['member_id']
        loan_account_id = payment_session['loan_account_id']
        amount = Decimal(payment_session['amount'])
        balance_before = Decimal(payment_session['balance_before'])
        
        # Verify payment with PesaPal
        pesapal = PesaPal()
        payment_status = pesapal.verify_transaction_status(order_tracking_id)
        
        if not payment_status:
            flash('Could not verify payment status', 'error')
            return redirect(url_for('member.loans'))
        
        # Normalize payment status
        payment_status_desc = payment_status.get('payment_status_description', '').upper()
        if 'COMPLETED' in payment_status_desc:
            normalized_status = 'completed'
        elif 'PENDING' in payment_status_desc:
            normalized_status = 'pending'
        else:
            normalized_status = 'failed'
        
        if normalized_status == 'completed':
            # Check if transaction already processed by looking at payment_method
            existing_transaction_res = supabase.table('loan_transactions')\
                .select('*')\
                .eq('id', transaction_id)\
                .execute()
            
            existing_transaction = existing_transaction_res.data[0] if existing_transaction_res.data else None
            
            if existing_transaction and existing_transaction.get('payment_method') == 'pesapal_completed':
                flash(f'Payment of UGX {amount:,.0f} was already processed!', 'info')
                return redirect(url_for('member.loans'))
            
            # Update loan account balance
            loan_res = supabase.table('loan_accounts')\
                .select('current_balance, available_limit')\
                .eq('id', loan_account_id)\
                .single()\
                .execute()
            
            loan_account = loan_res.data
            new_balance = Decimal(loan_account['current_balance']) - amount
            new_available = Decimal(loan_account['available_limit']) + amount
            
            # Update account balances
            supabase.table('loan_accounts')\
                .update({
                    'current_balance': str(new_balance),
                    'available_limit': str(new_available),
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', loan_account_id)\
                .execute()
            
            # Update the transaction using payment_method field
            supabase.table('loan_transactions')\
                .update({
                    'balance_before': str(balance_before),
                    'balance_after': str(new_balance),
                    'reference_number': merchant_reference or payment_session['reference_id'],
                    'payment_method': 'pesapal_completed',
                    'description': f'Loan balance payment completed via PesaPal'
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # Update payment session status
            supabase.table('loan_payment_sessions')\
                .update({
                    'status': 'completed',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            flash(f'Payment of UGX {amount:,.0f} completed successfully! Your loan balance is now UGX {new_balance:,.0f}', 'success')
            
        elif normalized_status == 'pending':
            # Update transaction status using payment_method
            supabase.table('loan_transactions')\
                .update({
                    'payment_method': 'pesapal_pending',
                    'description': f'Loan balance payment pending via PesaPal'
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # Update payment session
            supabase.table('loan_payment_sessions')\
                .update({
                    'status': 'pending',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            flash('Payment is pending confirmation. Your account will be updated once payment is confirmed.', 'info')
        
        else:
            # Update transaction as failed using payment_method
            supabase.table('loan_transactions')\
                .update({
                    'payment_method': 'pesapal_failed',
                    'description': f'Loan balance payment failed via PesaPal'
                })\
                .eq('id', transaction_id)\
                .execute()
            
            # Update payment session
            supabase.table('loan_payment_sessions')\
                .update({
                    'status': 'failed',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            flash('Payment failed. Please try again.', 'error')
        
        return redirect(url_for('member.loans'))
            
    except Exception as e:
        print(f"Error in balance callback: {e}")
        flash('Error processing payment callback', 'error')
        return redirect(url_for('member.loans'))
    


@member_bp.route('/statements')
@member_login_required
def statements():
    """Account statements"""
    try:
        member_id = session['member_id']
        
        # Initialize variables with defaults
        member = {}
        savings_account = {}
        loan_accounts = []
        savings_transactions = []
        loan_transactions = []
        repayments = []
        total_savings_deposits = Decimal(0)
        total_savings_withdrawals = Decimal(0)
        total_loan_repayments = Decimal(0)
        total_loan_disbursements = Decimal(0)

        # --- MEMBER DETAILS ---
        try:
            member_res = supabase.table('members') \
                .select('*') \
                .eq('id', member_id) \
                .single() \
                .execute()
            
            member = member_res.data or {}
        except Exception as e:
            print(f"Error getting member details: {e}")
            member = {
                'full_name': session.get('member_name', 'Member'),
                'member_number': session.get('member_number', ''),
                'email': session.get('member_email', '')
            }

        # --- SAVINGS ACCOUNT ---
        try:
            savings_res = supabase.table('savings_accounts') \
                .select('*') \
                .eq('member_id', member_id) \
                .single() \
                .execute()
            
            savings_account = savings_res.data or {}
        except Exception as e:
            print(f"Error getting savings account: {e}")
            savings_account = {}

        # --- LOAN ACCOUNTS (MAY BE MULTIPLE) ---
        try:
            loan_res = supabase.table('loan_accounts') \
                .select('id, account_number, current_balance, status') \
                .eq('member_id', member_id) \
                .execute()
            
            loan_accounts = loan_res.data or []
            loan_account_ids = [acc['id'] for acc in loan_accounts]
        except Exception as e:
            print(f"Error getting loan accounts: {e}")
            loan_accounts = []
            loan_account_ids = []

        # --- DATE RANGE ---
        start_date = request.args.get(
            'start_date',
            (datetime.now() - timedelta(days=30)).date().isoformat()
        )
        end_date = request.args.get(
            'end_date',
            datetime.now().date().isoformat()
        )

        # --- SAVINGS TRANSACTIONS ---
        if savings_account:
            try:
                savings_res = supabase.table('savings_transactions') \
                    .select('*') \
                    .eq('member_id', member_id) \
                    .gte('created_at', start_date) \
                    .lte('created_at', end_date) \
                    .order('created_at', desc=True) \
                    .execute()

                savings_transactions = savings_res.data or []

                for t in savings_transactions:
                    amount = Decimal(t.get('amount', '0'))
                    if t.get('transaction_type') == 'deposit':
                        total_savings_deposits += amount
                    elif t.get('transaction_type') == 'withdrawal':
                        total_savings_withdrawals += amount

            except Exception as e:
                print(f"Error getting savings transactions: {e}")
                savings_transactions = []

        # --- LOAN TRANSACTIONS (BY loan_account_id) ---
        if loan_account_ids:
            try:
                loan_tx_res = supabase.table('loan_transactions') \
                    .select('*') \
                    .in_('loan_account_id', loan_account_ids) \
                    .gte('created_at', start_date) \
                    .lte('created_at', end_date) \
                    .order('created_at', desc=True) \
                    .execute()

                loan_transactions = loan_tx_res.data or []

                for t in loan_transactions:
                    amount = Decimal(t.get('amount', '0'))
                    if t.get('transaction_type') == 'repayment':
                        total_loan_repayments += amount
                    elif t.get('transaction_type') == 'disbursement':
                        total_loan_disbursements += amount

            except Exception as e:
                print(f"Error getting loan transactions: {e}")
                loan_transactions = []

            # --- REPAYMENTS (OPTIONAL EXTRA) ---
            try:
                repayments_res = supabase.table('loan_repayments') \
                    .select('*, loan_applications(loan_amount, purpose)') \
                    .eq('member_id', member_id) \
                    .gte('paid_date', start_date) \
                    .lte('paid_date', end_date) \
                    .order('paid_date', desc=True) \
                    .execute()

                repayments = repayments_res.data or []

            except Exception as e:
                print(f"Error getting repayments: {e}")
                repayments = []

        return render_template(
            'member/statements.html',
            member=member,
            savings_account=savings_account,
            loan_account=loan_accounts,   # now supports multiple loans
            start_date=start_date,
            end_date=end_date,
            savings_transactions=savings_transactions,
            loan_transactions=loan_transactions,
            repayments=repayments,
            total_savings_deposits=total_savings_deposits,
            total_savings_withdrawals=total_savings_withdrawals,
            total_loan_repayments=total_loan_repayments,
            total_loan_disbursements=total_loan_disbursements
        )

    except Exception as e:
        print(f"Error loading statements: {e}")
        flash('Error loading statements', 'error')

        return render_template(
            'member/statements.html',
            member={'full_name': session.get('member_name', 'Member'),
                    'member_number': session.get('member_number', ''),
                    'email': session.get('member_email', '')},
            savings_account={},
            loan_account={},
            start_date=(datetime.now() - timedelta(days=30)).date().isoformat(),
            end_date=datetime.now().date().isoformat(),
            savings_transactions=[],
            loan_transactions=[],
            repayments=[],
            total_savings_deposits=0,
            total_savings_withdrawals=0,
            total_loan_repayments=0,
            total_loan_disbursements=0
        )

        
@member_bp.route('/download-statement', methods=['POST'])
@member_login_required
def download_statement():
    """Download statement as PDF"""
    try:
        member_id = session['member_id']
        statement_type = request.form.get('statement_type', 'combined')
        start_date = request.form.get('start_date', (datetime.now() - timedelta(days=30)).date().isoformat())
        end_date = request.form.get('end_date', datetime.now().date().isoformat())
        
        # Get member details
        member_res = supabase.table('members')\
            .select('*')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data if member_res.data else {}
        
        # Get savings account
        savings_res = supabase.table('savings_accounts')\
            .select('*')\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        savings_account = savings_res.data if savings_res.data else {}
        
        # Get loan account
        loan_res = supabase.table('loan_accounts')\
            .select('*')\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        loan_account = loan_res.data if loan_res.data else {}
        
        # Get transactions based on statement type
        data = {
            'member': member,
            'savings_account': savings_account,
            'loan_account': loan_account,
            'start_date': start_date,
            'end_date': end_date,
            'statement_type': statement_type,
            'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        if statement_type in ['combined', 'savings']:
            savings_res = supabase.table('savings_transactions')\
                .select('*')\
                .eq('member_id', member_id)\
                .gte('created_at', start_date)\
                .lte('created_at', end_date)\
                .order('created_at', desc=True)\
                .execute()
            
            data['savings_transactions'] = savings_res.data if savings_res.data else []
            
            # Calculate savings totals
            if data['savings_transactions']:
                deposits = [t for t in data['savings_transactions'] if t.get('transaction_type') == 'deposit']
                withdrawals = [t for t in data['savings_transactions'] if t.get('transaction_type') == 'withdrawal']
                data['total_deposits'] = sum(Decimal(t['amount']) for t in deposits)
                data['total_withdrawals'] = sum(Decimal(t['amount']) for t in withdrawals)
        
        if statement_type in ['combined', 'loan']:
            loan_res = supabase.table('loan_transactions')\
                .select('*')\
                .eq('member_id', member_id)\
                .gte('created_at', start_date)\
                .lte('created_at', end_date)\
                .order('created_at', desc=True)\
                .execute()
            
            data['loan_transactions'] = loan_res.data if loan_res.data else []
            
            # Calculate loan totals
            if data['loan_transactions']:
                repayments = [t for t in data['loan_transactions'] if t.get('transaction_type') == 'repayment']
                disbursements = [t for t in data['loan_transactions'] if t.get('transaction_type') == 'disbursement']
                data['total_repayments'] = sum(Decimal(t['amount']) for t in repayments)
                data['total_disbursements'] = sum(Decimal(t['amount']) for t in disbursements)
            
            # Get repayments
            repayments_res = supabase.table('loan_repayments')\
                .select('*, loan_applications(loan_amount, purpose)')\
                .eq('member_id', member_id)\
                .gte('paid_date', start_date)\
                .lte('paid_date', end_date)\
                .order('paid_date', desc=True)\
                .execute()
            
            data['repayments'] = repayments_res.data if repayments_res.data else []
        
        # Generate PDF
        pdf = generate_statement_pdf(data)
        
        # Create response
        filename = f"statement_{member.get('member_number', 'member')}_{start_date}_to_{end_date}.pdf"
        
        return Response(
            pdf,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'application/pdf'
            }
        )
        
    except Exception as e:
        print(f"Error generating statement PDF: {e}")
        flash('Error generating statement', 'error')
        return redirect(url_for('member.statements'))

def generate_statement_pdf(data):
    """Generate PDF from HTML template"""
    try:
        # Render HTML template
        html = render_template('member/statement_pdf.html', **data)
        
        # Create PDF
        pdf = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf)
        
        if pisa_status.err:
            raise Exception(f"PDF generation error: {pisa_status.err}")
        
        pdf.seek(0)
        return pdf.getvalue()
        
    except Exception as e:
        print(f"Error in PDF generation: {e}")
        raise
    
@member_bp.route('/preview-statement', methods=['POST'])
@member_login_required
def preview_statement():
    """Preview statement before download"""
    try:
        member_id = session['member_id']
        statement_type = request.form.get('statement_type', 'combined')
        start_date = request.form.get(
            'start_date',
            (datetime.now() - timedelta(days=30)).date().isoformat()
        )
        end_date = request.form.get(
            'end_date',
            datetime.now().date().isoformat()
        )

        # ---- MEMBER DETAILS ----
        member_res = supabase.table('members') \
            .select('*') \
            .eq('id', member_id) \
            .single() \
            .execute()
        member = member_res.data or {}

        # ---- SAVINGS ACCOUNT ----
        savings_res = supabase.table('savings_accounts') \
            .select('*') \
            .eq('member_id', member_id) \
            .single() \
            .execute()
        savings_account = savings_res.data or {}

        # ---- LOAN ACCOUNT ---- (single loan per member)
        loan_res = supabase.table('loan_accounts') \
            .select('*') \
            .eq('member_id', member_id) \
            .single() \
            .execute()
        loan_account = loan_res.data or {}
        loan_account_id = loan_account.get('id')  # for transactions

        transactions_data = {
            'member': member,
            'savings_account': savings_account,
            'loan_account': loan_account,
            'start_date': start_date,
            'end_date': end_date,
            'statement_type': statement_type
        }

        # ---- SAVINGS TRANSACTIONS ----
        if statement_type in ['combined', 'savings'] and savings_account:
            savings_tx = supabase.table('savings_transactions') \
                .select('*') \
                .eq('member_id', member_id) \
                .gte('created_at', start_date) \
                .lte('created_at', end_date) \
                .order('created_at', desc=True) \
                .limit(5) \
                .execute()
            transactions_data['savings_transactions'] = savings_tx.data or []

        # ---- LOAN TRANSACTIONS ----
        if statement_type in ['combined', 'loan'] and loan_account_id:
            loan_tx = supabase.table('loan_transactions') \
                .select('*') \
                .eq('loan_account_id', loan_account_id) \
                .gte('created_at', start_date) \
                .lte('created_at', end_date) \
                .order('created_at', desc=True) \
                .limit(5) \
                .execute()
            transactions_data['loan_transactions'] = loan_tx.data or []

            # ---- REPAYMENTS ----
            repayments_tx = supabase.table('loan_repayments') \
                .select('*, loan_applications(loan_amount, purpose)') \
                .eq('member_id', member_id) \
                .gte('paid_date', start_date) \
                .lte('paid_date', end_date) \
                .order('paid_date', desc=True) \
                .limit(5) \
                .execute()
            transactions_data['repayments'] = repayments_tx.data or []

        # ---- RENDER PREVIEW ----
        html = render_template('member/statement_preview.html', **transactions_data)

        return jsonify({
            'success': True,
            'html': html,
            'statement_type': statement_type,
            'start_date': start_date,
            'end_date': end_date
        })

    except Exception as e:
        print(f"Error previewing statement: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


    
@member_bp.route('/shares')
@member_login_required
def shares():
    """Share purchase page"""
    try:
        member_id = session['member_id']
        
        # Get member details
        member_res = supabase.table('members')\
            .select('full_name, email, shares_owned')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data
        
        # Get current share value
        share_value_res = supabase.table('share_value')\
            .select('*')\
            .order('effective_date', desc=True)\
            .limit(1)\
            .execute()
        
        share_value = share_value_res.data[0] if share_value_res.data else {'value_per_share': 1000, 'currency': 'UGX'}
        
        # Get share transactions history
        transactions_res = supabase.table('share_transactions')\
            .select('*')\
            .eq('member_id', member_id)\
            .order('transaction_date', desc=True)\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        
        return render_template('member/shares.html',
                             member=member,
                             share_value=share_value,
                             transactions=transactions)
        
    except Exception as e:
        print(f"Error loading shares page: {e}")
        flash('Error loading shares information', 'error')
        return render_template('member/shares.html')
    
@member_bp.route('/purchase-shares', methods=['POST'])
@member_login_required
def purchase_shares():
    """Purchase shares via PesaPal"""
    try:
        member_id = session['member_id']
        shares_to_buy = int(request.form.get('shares', '0'))
        
        if shares_to_buy <= 0:
            flash('Please enter a valid number of shares', 'error')
            return redirect(url_for('member.shares'))
        
        # Get current share value
        share_value_res = supabase.table('share_value')\
            .select('*')\
            .order('effective_date', desc=True)\
            .limit(1)\
            .execute()
        
        if not share_value_res.data:
            flash('Share price not configured. Please contact admin.', 'error')
            return redirect(url_for('member.shares'))
        
        share_value = share_value_res.data[0]
        price_per_share = Decimal(share_value['value_per_share'])
        total_amount = price_per_share * shares_to_buy
        
        # Get member details
        member_res = supabase.table('members')\
            .select('full_name, email, phone_number')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data
        
        # Create share transaction record WITHOUT total_amount (it's generated)
        transaction_id = str(uuid.uuid4())
        transaction_data = {
            'member_id': member_id,
            'shares': shares_to_buy,
            'price_per_share': str(price_per_share),
            'currency': share_value['currency'],
            'transaction_type': 'purchase',
            'reference': f'SHARE-{transaction_id[:8].upper()}',
            'notes': f'Purchase of {shares_to_buy} shares at UGX {price_per_share:,.0f} per share',
            'transaction_date': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Try to insert without total_amount first
        try:
            supabase.table('share_transactions').insert(transaction_data).execute()
        except Exception as insert_error:
            print(f"Insert error: {insert_error}")
            # Check if error is about total_amount column
            error_msg = str(insert_error)
            if 'total_amount' in error_msg.lower():
                print("total_amount is a generated column, trying insert without it...")
                # Remove total_amount if it was accidentally added
                if 'total_amount' in transaction_data:
                    del transaction_data['total_amount']
                # Try insert again
                supabase.table('share_transactions').insert(transaction_data).execute()
            else:
                # Re-raise if it's a different error
                raise insert_error
        
        # Initialize PesaPal
        pesapal = PesaPal()
        
        # Prepare payment details
        reference_id = f"SHARE-{transaction_id[:8].upper()}"
        
        # Extract names for billing
        names = member['full_name'].split()
        first_name = names[0] if names else "Member"
        last_name = names[-1] if len(names) > 1 else "User"
        
        # Get callback URL
        callback_url = url_for('member.share_payment_callback', _external=True)
        
        # Submit order to PesaPal
        order = pesapal.submit_order(
            amount=float(total_amount),
            reference_id=reference_id,
            callback_url=callback_url,
            email=member['email'],
            first_name=first_name,
            last_name=last_name
        )
        
        if order and order.get('redirect_url'):
            # Update transaction with PesaPal order ID
            supabase.table('share_transactions')\
                .update({
                    'reference': reference_id,
                    'notes': f'Purchase of {shares_to_buy} shares at UGX {price_per_share:,.0f} per share - Pending PesaPal Payment',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('reference', f'SHARE-{transaction_id[:8].upper()}')\
                .execute()
            
            # Store in payment sessions
            payment_session_data = {
                'transaction_id': transaction_id,
                'member_id': member_id,
                'order_tracking_id': order['order_tracking_id'],
                'reference_id': reference_id,
                'shares': shares_to_buy,
                'price_per_share': str(price_per_share),
                'total_amount': str(total_amount),
                'currency': share_value['currency'],
                'status': 'pending',
                'created_at': datetime.now().isoformat()
            }
            
            supabase.table('share_payment_sessions').insert(payment_session_data).execute()
            
            # Redirect to PesaPal
            return redirect(order['redirect_url'])
        else:
            # Update transaction as failed
            supabase.table('share_transactions')\
                .update({
                    'notes': f'Purchase failed - PesaPal initialization error',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('reference', f'SHARE-{transaction_id[:8].upper()}')\
                .execute()
            
            flash('Failed to initiate payment. Please try again.', 'error')
            return redirect(url_for('member.shares'))
            
    except Exception as e:
        print(f"Error initiating share purchase: {e}")
        flash('Error initiating share purchase', 'error')
        return redirect(url_for('member.shares'))
    
    
@member_bp.route('/share-payment-callback', methods=['GET'])
@member_login_required
def share_payment_callback():
    """Handle PesaPal callback for share purchase"""
    try:
        order_tracking_id = request.args.get('OrderTrackingId')
        merchant_reference = request.args.get('OrderMerchantReference')
        
        if not order_tracking_id:
            flash('Invalid payment callback', 'error')
            return redirect(url_for('member.shares'))
        
        # Get payment session
        payment_session_res = supabase.table('share_payment_sessions')\
            .select('*')\
            .eq('order_tracking_id', order_tracking_id)\
            .single()\
            .execute()
        
        if not payment_session_res.data:
            flash('Payment session not found', 'error')
            return redirect(url_for('member.shares'))
        
        payment_session = payment_session_res.data
        member_id = payment_session['member_id']
        shares_to_buy = payment_session['shares']
        price_per_share = Decimal(payment_session['price_per_share'])
        total_amount = Decimal(payment_session['total_amount'])
        
        # Verify payment with PesaPal
        pesapal = PesaPal()
        payment_status = pesapal.verify_transaction_status(order_tracking_id)
        
        if not payment_status:
            flash('Could not verify payment status', 'error')
            return redirect(url_for('member.shares'))
        
        # Normalize payment status
        payment_status_desc = payment_status.get('payment_status_description', '').upper()
        if 'COMPLETED' in payment_status_desc:
            normalized_status = 'completed'
        elif 'PENDING' in payment_status_desc:
            normalized_status = 'pending'
        else:
            normalized_status = 'failed'
        
        if normalized_status == 'completed':
            # Check if already processed
            existing_session_res = supabase.table('share_payment_sessions')\
                .select('*')\
                .eq('order_tracking_id', order_tracking_id)\
                .eq('status', 'completed')\
                .execute()
            
            if existing_session_res.data:
                flash(f'Purchase of {shares_to_buy} shares was already processed!', 'info')
                return redirect(url_for('member.shares'))
            
            # Get current member shares
            member_res = supabase.table('members')\
                .select('shares_owned')\
                .eq('id', member_id)\
                .single()\
                .execute()
            
            member_data = member_res.data
            current_shares = member_data.get('shares_owned', 0)
            new_shares = current_shares + shares_to_buy
            
            # Update member shares
            supabase.table('members')\
                .update({
                    'shares_owned': new_shares,
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', member_id)\
                .execute()
            
            # Update share transaction (don't try to update total_amount if it's generated)
            update_data = {
                'reference': merchant_reference or payment_session['reference_id'],
                'notes': f'Purchase of {shares_to_buy} shares at UGX {price_per_share:,.0f} per share - Completed via PesaPal',
                'updated_at': datetime.now().isoformat()
            }
            
            # Try to update, but don't include total_amount
            supabase.table('share_transactions')\
                .update(update_data)\
                .eq('reference', payment_session['reference_id'])\
                .execute()
            
            # Update payment session
            supabase.table('share_payment_sessions')\
                .update({
                    'status': 'completed',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            flash(f'Successfully purchased {shares_to_buy} shares for UGX {total_amount:,.0f}! You now own {new_shares} shares.', 'success')
            
        elif normalized_status == 'pending':
            # Update payment session
            supabase.table('share_payment_sessions')\
                .update({
                    'status': 'pending',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            flash('Payment is pending confirmation. Your shares will be updated once payment is confirmed.', 'info')
        
        else:
            # Update payment session
            supabase.table('share_payment_sessions')\
                .update({
                    'status': 'failed',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('order_tracking_id', order_tracking_id)\
                .execute()
            
            # Update transaction
            supabase.table('share_transactions')\
                .update({
                    'notes': f'Purchase of {shares_to_buy} shares at UGX {price_per_share:,.0f} per share - Payment failed via PesaPal',
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('reference', payment_session['reference_id'])\
                .execute()
            
            flash('Payment failed. Please try again.', 'error')
        
        return redirect(url_for('member.shares'))
            
    except Exception as e:
        print(f"Error in share payment callback: {e}")
        flash('Error processing payment callback', 'error')
        return redirect(url_for('member.shares'))