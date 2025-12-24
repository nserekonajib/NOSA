import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from functools import wraps
from supabase import create_client, Client
from datetime import datetime, timedelta
import uuid
import json
from decimal import Decimal
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Create Blueprint
loans_bp = Blueprint('loans', __name__, url_prefix='/admin/loans')

# Admin required decorator
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session.get('admin_logged_in'):
            flash('Please login to access this page', 'error')
            return redirect(url_for('adminauth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper functions
def decimal_to_str(obj):
    """Convert Decimal objects to string for JSON serialization"""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: decimal_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decimal_to_str(item) for item in obj]
    return obj

def calculate_loan_schedule(amount, interest_rate, months):
    """Calculate loan amortization schedule"""
    monthly_rate = (Decimal(interest_rate) / Decimal(100)) / Decimal(12)
    monthly_payment = amount * (monthly_rate * (1 + monthly_rate) ** months) / ((1 + monthly_rate) ** months - 1)
    
    schedule = []
    balance = amount
    
    for i in range(1, months + 1):
        interest = balance * monthly_rate
        principal = monthly_payment - interest
        balance -= principal
        
        schedule.append({
            'installment_number': i,
            'due_amount': float(monthly_payment),
            'principal': float(principal),
            'interest': float(interest),
            'balance': float(balance)
        })
    
    return schedule, float(monthly_payment), float(amount * (1 + monthly_rate) ** months)

# Routes
@loans_bp.route('/products')
@admin_login_required
def loan_products():
    """View all loan products"""
    try:
        # Get loan products
        products_res = supabase.table('loan_products')\
            .select('*')\
            .order('created_at', desc=True)\
            .execute()
        
        products = products_res.data if products_res.data else []
        
        # Get counts
        counts_res = supabase.table('loan_products')\
            .select('status', count='exact')\
            .execute()
        
        return render_template('admin/loans/products.html', 
                             products=products,
                             total_count=len(products))
        
    except Exception as e:
        print(f"Error fetching loan products: {e}")
        flash('Error loading loan products', 'error')
        return render_template('admin/loans/products.html', products=[])

@loans_bp.route('/products/add', methods=['GET', 'POST'])
@admin_login_required
def add_loan_product():
    """Add new loan product"""
    if request.method == 'POST':
        try:
            product_data = {
                'name': request.form.get('name', '').strip(),
                'description': request.form.get('description', '').strip(),
                'interest_rate': request.form.get('interest_rate', '0'),
                'min_amount': request.form.get('min_amount', '0'),
                'max_amount': request.form.get('max_amount', '0'),
                'repayment_period_months': request.form.get('repayment_period_months', '12'),
                'processing_fee': request.form.get('processing_fee', '0'),
                'insurance_fee': request.form.get('insurance_fee', '0'),
                'grace_period_days': request.form.get('grace_period_days', '0'),
                'penalty_rate': request.form.get('penalty_rate', '0'),
                'status': request.form.get('status', 'active'),
                'created_by': session.get('admin_id'),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Handle requirements as array
            requirements = request.form.getlist('requirements[]')
            if requirements:
                product_data['requirements'] = requirements
            
            # Handle eligibility criteria
            eligibility = {}
            if request.form.get('min_age'):
                eligibility['min_age'] = request.form.get('min_age')
            if request.form.get('min_savings_balance'):
                eligibility['min_savings_balance'] = request.form.get('min_savings_balance')
            if request.form.get('min_membership_months'):
                eligibility['min_membership_months'] = request.form.get('min_membership_months')
            
            if eligibility:
                product_data['eligibility_criteria'] = eligibility
            
            # Validate required fields
            required_fields = ['name', 'interest_rate', 'min_amount', 'max_amount', 'repayment_period_months']
            missing_fields = [field for field in required_fields if not product_data[field]]
            
            if missing_fields:
                flash(f"Missing required fields: {', '.join(missing_fields)}", 'error')
                return render_template('admin/loans/add_product.html', form_data=product_data)
            
            # Insert into database
            response = supabase.table('loan_products').insert(product_data).execute()
            
            if not response.data:
                flash('Failed to create loan product', 'error')
                return render_template('admin/loans/add_product.html', form_data=product_data)
            
            flash('Loan product created successfully', 'success')
            return redirect(url_for('loans.loan_products'))
            
        except Exception as e:
            print(f"Error creating loan product: {e}")
            flash('Error creating loan product', 'error')
            return render_template('admin/loans/add_product.html', form_data=product_data if 'product_data' in locals() else {})
    
    return render_template('admin/loans/add_product.html')

@loans_bp.route('/products/edit/<product_id>', methods=['GET', 'POST'])
@admin_login_required
def edit_loan_product(product_id):
    """Edit loan product"""
    try:
        if request.method == 'POST':
            product_data = {
                'name': request.form.get('name', '').strip(),
                'description': request.form.get('description', '').strip(),
                'interest_rate': request.form.get('interest_rate', '0'),
                'min_amount': request.form.get('min_amount', '0'),
                'max_amount': request.form.get('max_amount', '0'),
                'repayment_period_months': request.form.get('repayment_period_months', '12'),
                'processing_fee': request.form.get('processing_fee', '0'),
                'insurance_fee': request.form.get('insurance_fee', '0'),
                'grace_period_days': request.form.get('grace_period_days', '0'),
                'penalty_rate': request.form.get('penalty_rate', '0'),
                'status': request.form.get('status', 'active'),
                'updated_at': datetime.now().isoformat()
            }
            
            # Handle requirements
            requirements = request.form.getlist('requirements[]')
            if requirements:
                product_data['requirements'] = requirements
            
            # Handle eligibility criteria
            eligibility = {}
            if request.form.get('min_age'):
                eligibility['min_age'] = request.form.get('min_age')
            if request.form.get('min_savings_balance'):
                eligibility['min_savings_balance'] = request.form.get('min_savings_balance')
            if request.form.get('min_membership_months'):
                eligibility['min_membership_months'] = request.form.get('min_membership_months')
            
            if eligibility:
                product_data['eligibility_criteria'] = eligibility
            
            # Update product
            supabase.table('loan_products').update(product_data).eq('id', product_id).execute()
            
            flash('Loan product updated successfully', 'success')
            return redirect(url_for('loans.loan_products'))
        
        # GET request - load product data
        product_res = supabase.table('loan_products').select('*').eq('id', product_id).single().execute()
        
        if not product_res.data:
            flash('Loan product not found', 'error')
            return redirect(url_for('loans.loan_products'))
        
        product = product_res.data
        return render_template('admin/loans/edit_product.html', product=product)
        
    except Exception as e:
        print(f"Error editing loan product: {e}")
        flash('Error editing loan product', 'error')
        return redirect(url_for('loans.loan_products'))

@loans_bp.route('/products/delete/<product_id>', methods=['POST'])
@admin_login_required
def delete_loan_product(product_id):
    """Delete loan product"""
    try:
        # Check if product has any applications
        apps_res = supabase.table('loan_applications').select('id').eq('loan_product_id', product_id).limit(1).execute()
        
        if apps_res.data:
            flash('Cannot delete product with existing loan applications', 'error')
            return redirect(url_for('loans.loan_products'))
        
        # Delete product
        supabase.table('loan_products').delete().eq('id', product_id).execute()
        
        flash('Loan product deleted successfully', 'success')
        return redirect(url_for('loans.loan_products'))
        
    except Exception as e:
        print(f"Error deleting loan product: {e}")
        flash('Error deleting loan product', 'error')
        return redirect(url_for('loans.loan_products'))

@loans_bp.route('/applications')
@admin_login_required
def loan_applications():
    """View all loan applications"""
    try:
        # Get query parameters
        status = request.args.get('status', '')
        search = request.args.get('search', '')
        
        # Build query
        query = supabase.table('loan_applications')\
            .select('*, members(full_name, member_number), loan_products(name)')\
            .order('created_at', desc=True)
        
        if status:
            query = query.eq('status', status)
        
        if search:
            query = query.or_(f"account_number.ilike.%{search}%,members.full_name.ilike.%{search}%")
        
        response = query.execute()
        applications = response.data if response.data else []
        
        # Get counts by status
        counts_res = supabase.table('loan_applications')\
            .select('status', count='exact')\
            .execute()
        
        return render_template('admin/loans/applications.html',
                             applications=applications,
                             status=status,
                             search=search,
                             total_count=len(applications))
        
    except Exception as e:
        print(f"Error fetching loan applications: {e}")
        flash('Error loading loan applications', 'error')
        return render_template('admin/loans/applications.html', applications=[])

@loans_bp.route('/applications/view/<application_id>')
@admin_login_required
def view_application(application_id):
    """View loan application details"""
    try:
        # Get application details
        app_res = supabase.table('loan_applications')\
            .select('*, members(*), loan_products(*)')\
            .eq('id', application_id)\
            .single()\
            .execute()
        
        if not app_res.data:
            flash('Loan application not found', 'error')
            return redirect(url_for('loans.loan_applications'))
        
        application = app_res.data
        
        # Get member's loan account
        loan_account_res = supabase.table('loan_accounts')\
            .select('*')\
            .eq('member_id', application['member_id'])\
            .single()\
            .execute()
        
        loan_account = loan_account_res.data if loan_account_res.data else None
        
        # Get repayment schedule if approved
        repayments = []
        if application['status'] in ['approved', 'disbursed']:
            repayments_res = supabase.table('loan_repayments')\
                .select('*')\
                .eq('loan_application_id', application_id)\
                .order('installment_number')\
                .execute()
            
            repayments = repayments_res.data if repayments_res.data else []
        
        # Get transaction history
        transactions_res = supabase.table('loan_transactions')\
            .select('*')\
            .eq('loan_application_id', application_id)\
            .order('created_at', desc=True)\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        
        return render_template('admin/loans/application_details.html',
                             application=application,
                             loan_account=loan_account,
                             repayments=repayments,
                             transactions=transactions)
        
    except Exception as e:
        print(f"Error viewing loan application: {e}")
        flash('Error loading application details', 'error')
        return redirect(url_for('loans.loan_applications'))

@loans_bp.route('/applications/approve/<application_id>', methods=['POST'])
@admin_login_required
def approve_application(application_id):
    """Approve loan application"""
    try:
        # Get application
        app_res = supabase.table('loan_applications')\
            .select('*')\
            .eq('id', application_id)\
            .single()\
            .execute()
        
        if not app_res.data:
            return jsonify({'success': False, 'message': 'Application not found'}), 404
        
        application = app_res.data
        
        # Check if already processed
        if application['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Application already processed'}), 400
        
        # Update application status
        update_data = {
            'status': 'approved',
            'approved_by': session.get('admin_id'),
            'approved_at': datetime.now().isoformat(),
            'remarks': request.form.get('remarks', ''),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('loan_applications').update(update_data).eq('id', application_id).execute()
        
        # Create repayment schedule
        schedule, monthly_payment, total_repayable = calculate_loan_schedule(
            Decimal(application['loan_amount']),
            Decimal(application['interest_rate']),
            application['repayment_period_months']
        )
        
        # Update with calculated amounts
        supabase.table('loan_applications')\
            .update({
                'monthly_installment': str(monthly_payment),
                'total_repayable': str(total_repayable)
            })\
            .eq('id', application_id)\
            .execute()
        
        # Create repayment schedule in database
        start_date = datetime.now() + timedelta(days=30)  # First payment due in 30 days
        repayment_data = []
        
        for i, installment in enumerate(schedule):
            due_date = start_date + timedelta(days=30*i)
            
            repayment_data.append({
                'loan_application_id': application_id,
                'member_id': application['member_id'],
                'installment_number': installment['installment_number'],
                'due_date': due_date.date().isoformat(),
                'due_amount': str(installment['due_amount']),
                'principal_amount': str(installment['principal']),
                'interest_amount': str(installment['interest']),
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            })
        
        if repayment_data:
            supabase.table('loan_repayments').insert(repayment_data).execute()
        
        # Log activity
        log_loan_activity(application_id, 'application_approved', 
                         f'Loan application approved by admin. Amount: {application["loan_amount"]}')
        
        return jsonify({
            'success': True,
            'message': 'Application approved successfully'
        })
        
    except Exception as e:
        print(f"Error approving application: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@loans_bp.route('/applications/reject/<application_id>', methods=['POST'])
@admin_login_required
def reject_application(application_id):
    """Reject loan application"""
    try:
        # Get application
        app_res = supabase.table('loan_applications')\
            .select('*')\
            .eq('id', application_id)\
            .single()\
            .execute()
        
        if not app_res.data:
            return jsonify({'success': False, 'message': 'Application not found'}), 404
        
        application = app_res.data
        
        # Check if already processed
        if application['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Application already processed'}), 400
        
        # Update application status
        update_data = {
            'status': 'rejected',
            'rejected_by': session.get('admin_id'),
            'rejected_at': datetime.now().isoformat(),
            'remarks': request.form.get('remarks', ''),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('loan_applications').update(update_data).eq('id', application_id).execute()
        
        # Log activity
        log_loan_activity(application_id, 'application_rejected', 
                         f'Loan application rejected by admin. Amount: {application["loan_amount"]}')
        
        return jsonify({
            'success': True,
            'message': 'Application rejected successfully'
        })
        
    except Exception as e:
        print(f"Error rejecting application: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@loans_bp.route('/applications/disburse/<application_id>', methods=['POST'])
@admin_login_required
def disburse_loan(application_id):
    """Disburse approved loan"""
    try:
        # Get application
        app_res = supabase.table('loan_applications')\
            .select('*')\
            .eq('id', application_id)\
            .single()\
            .execute()
        
        if not app_res.data:
            return jsonify({'success': False, 'message': 'Application not found'}), 404
        
        application = app_res.data
        
        # Check if can be disbursed
        if application['status'] != 'approved':
            return jsonify({'success': False, 'message': 'Only approved applications can be disbursed'}), 400
        
        # Get member's loan account
        loan_account_res = supabase.table('loan_accounts')\
            .select('*')\
            .eq('member_id', application['member_id'])\
            .single()\
            .execute()
        
        if not loan_account_res.data:
            return jsonify({'success': False, 'message': 'Member loan account not found'}), 404
        
        loan_account = loan_account_res.data
        
        # Get disbursement details
        disbursement_method = request.form.get('disbursement_method', '')
        reference_number = request.form.get('reference_number', '')
        
        if not disbursement_method:
            return jsonify({'success': False, 'message': 'Disbursement method required'}), 400
        
        # Calculate net disbursement
        loan_amount = Decimal(application['loan_amount'])
        processing_fee = Decimal(application.get('processing_fee', '0') or '0')
        insurance_fee = Decimal(application.get('insurance_fee', '0') or '0')
        net_disbursement = loan_amount - processing_fee - insurance_fee
        
        # Update application
        update_data = {
            'status': 'disbursed',
            'disbursed_at': datetime.now().isoformat(),
            'disbursement_method': disbursement_method,
            'disbursement_reference': reference_number,
            'net_disbursement': str(net_disbursement),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('loan_applications').update(update_data).eq('id', application_id).execute()
        
        # Update loan account balance
        current_balance = Decimal(loan_account.get('current_balance', '0') or '0')
        new_balance = current_balance + loan_amount
        
        supabase.table('loan_accounts')\
            .update({
                'current_balance': str(new_balance),
                'available_limit': str(Decimal(loan_account.get('credit_limit', '0') or '0') - new_balance),
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', loan_account['id'])\
            .execute()
        
        # Create transaction record
        transaction_data = {
    'loan_account_id': loan_account['id'],  # Changed from member_id
    'transaction_type': 'disbursement',
    'amount': str(loan_amount),
    'balance_before': str(current_balance),
    'balance_after': str(new_balance),
    'reference_number': reference_number,
    'description': f'Loan disbursement - {application.get("purpose", "")}',
    'payment_method': disbursement_method,
    'processed_by': session.get('admin_id'),
    'created_at': datetime.now().isoformat()
}
        
        supabase.table('loan_transactions').insert(transaction_data).execute()
        
        # Log activity
        log_loan_activity(application_id, 'loan_disbursed', 
                         f'Loan disbursed: {loan_amount}. Method: {disbursement_method}')
        
        return jsonify({
            'success': True,
            'message': 'Loan disbursed successfully'
        })
        
    except Exception as e:
        print(f"Error disbursing loan: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@loans_bp.route('/repayments')
@admin_login_required
def loan_repayments():
    """View loan repayments"""
    try:
        # Get query parameters
        status = request.args.get('status', '')
        search = request.args.get('search', '')
        
        # Build query
        query = supabase.table('loan_repayments')\
            .select('*, loan_applications(account_number, loan_amount), members(full_name, member_number)')\
            .order('due_date')\
            .limit(100)
        
        if status:
            query = query.eq('status', status)
        
        if search:
            query = query.or_(f"members.full_name.ilike.%{search}%,loan_applications.account_number.ilike.%{search}%")
        
        response = query.execute()
        repayments = response.data if response.data else []
        
        # Get summary statistics
        summary_res = supabase.table('loan_repayments')\
            .select('status', count='exact')\
            .execute()
        
        # Calculate totals
        total_due = sum(Decimal(r.get('due_amount', '0') or '0') for r in repayments)
        total_paid = sum(Decimal(r.get('paid_amount', '0') or '0') for r in repayments)
        
        return render_template('admin/loans/repayments.html',
                             repayments=repayments,
                             status=status,
                             search=search,
                             total_due=total_due,
                             total_paid=total_paid)
        
    except Exception as e:
        print(f"Error fetching loan repayments: {e}")
        flash('Error loading loan repayments', 'error')
        return render_template('admin/loans/repayments.html', repayments=[])

@loans_bp.route('/repayments/record/<repayment_id>', methods=['POST'])
@admin_login_required
def record_repayment(repayment_id):
    """Record loan repayment"""
    try:
        # Get repayment details
        repayment_res = supabase.table('loan_repayments')\
            .select('*, loan_applications(*), members(*)')\
            .eq('id', repayment_id)\
            .single()\
            .execute()
        
        if not repayment_res.data:
            return jsonify({'success': False, 'message': 'Repayment not found'}), 404
        
        repayment = repayment_res.data
        
        # Check if already paid
        if repayment['status'] == 'paid':
            return jsonify({'success': False, 'message': 'Repayment already recorded as paid'}), 400
        
        # Get payment details
        paid_amount = Decimal(request.form.get('paid_amount', '0'))
        payment_method = request.form.get('payment_method', '')
        reference_number = request.form.get('reference_number', '')
        
        if paid_amount <= 0:
            return jsonify({'success': False, 'message': 'Invalid payment amount'}), 400
        
        if not payment_method:
            return jsonify({'success': False, 'message': 'Payment method required'}), 400
        
        # Calculate late fees if applicable
        due_date = datetime.fromisoformat(repayment['due_date'].replace('Z', '+00:00'))
        today = datetime.now()
        late_days = max(0, (today - due_date).days)
        
        late_fee = Decimal('0')
        if late_days > 0:
            # Calculate late fee (example: 1% per month)
            monthly_penalty_rate = Decimal('0.01')
            late_fee = Decimal(repayment['due_amount']) * (monthly_penalty_rate / Decimal(30)) * Decimal(late_days)
        
        # Update repayment record
        update_data = {
            'paid_amount': str(paid_amount),
            'paid_date': today.date().isoformat(),
            'payment_method': payment_method,
            'reference_number': reference_number,
            'status': 'paid',
            'late_days': late_days,
            'late_fee': str(late_fee),
            'remarks': request.form.get('remarks', ''),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('loan_repayments').update(update_data).eq('id', repayment_id).execute()
        
        # Get loan account
        loan_account_res = supabase.table('loan_accounts')\
            .select('*')\
            .eq('member_id', repayment['member_id'])\
            .single()\
            .execute()
        
        if loan_account_res.data:
            loan_account = loan_account_res.data
            
            # Update loan account balance
            current_balance = Decimal(loan_account.get('current_balance', '0') or '0')
            new_balance = max(Decimal('0'), current_balance - Decimal(repayment['principal_amount']))
            
            supabase.table('loan_accounts')\
                .update({
                    'current_balance': str(new_balance),
                    'available_limit': str(Decimal(loan_account.get('credit_limit', '0') or '0') - new_balance),
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', loan_account['id'])\
                .execute()
            
            # Create transaction record
            transaction_data = {
                    'loan_account_id': loan_account['id'],  # Changed from member_id
                    'transaction_type': 'repayment',
                    'amount': str(paid_amount),
                    'balance_before': str(current_balance),
                    'balance_after': str(new_balance),
                    'reference_number': reference_number,
                    'description': f'Loan repayment - Installment #{repayment["installment_number"]}',
                    'payment_method': payment_method,
                    'processed_by': session.get('admin_id'),
                    'created_at': datetime.now().isoformat()
                }
            supabase.table('loan_transactions').insert(transaction_data).execute()
            
        # Log activity
        log_loan_activity(repayment['loan_application_id'], 'repayment_recorded', 
                         f'Repayment recorded: {paid_amount}. Installment: #{repayment["installment_number"]}')
        
        return jsonify({
            'success': True,
            'message': 'Repayment recorded successfully'
        })
        
    except Exception as e:
        print(f"Error recording repayment: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@loans_bp.route('/direct-loan', methods=['GET', 'POST'])
@admin_login_required
def direct_loan():
    """Direct loan issuance without application"""
    if request.method == 'POST':
        try:
            # Get form data
            member_id = request.form.get('member_id')
            loan_amount = Decimal(request.form.get('loan_amount', '0'))
            interest_rate = Decimal(request.form.get('interest_rate', '0'))
            repayment_months = int(request.form.get('repayment_months', '12'))
            purpose = request.form.get('purpose', '')
            disbursement_method = request.form.get('disbursement_method', '')
            reference_number = request.form.get('reference_number', '')
            
            # Validate
            if not member_id or loan_amount <= 0:
                flash('Invalid member or loan amount', 'error')
                return redirect(url_for('loans.direct_loan'))
            
            # Get member details
            member_res = supabase.table('members').select('*').eq('id', member_id).single().execute()
            if not member_res.data:
                flash('Member not found', 'error')
                return redirect(url_for('loans.direct_loan'))
            
            member = member_res.data
            
            # Get or create loan account
            loan_account_res = supabase.table('loan_accounts')\
                .select('*')\
                .eq('member_id', member_id)\
                .single()\
                .execute()
            
            if not loan_account_res.data:
                # Create loan account
                loan_account_data = {
                    'member_id': member_id,
                    'account_number': f"LA{member.get('member_number', '')}",
                    'credit_limit': '1000000.00',
                    'current_balance': '0.00',
                    'available_limit': '1000000.00',
                    'interest_rate': str(interest_rate),
                    'max_loan_amount': '5000000.00',
                    'min_loan_amount': '10000.00',
                    'repayment_period_months': 12,
                    'status': 'active',
                    'opened_at': datetime.now().isoformat(),
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                
                loan_account_res = supabase.table('loan_accounts').insert(loan_account_data).execute()
                loan_account = loan_account_res.data[0] if loan_account_res.data else None
            else:
                loan_account = loan_account_res.data
            
            if not loan_account:
                flash('Failed to create loan account', 'error')
                return redirect(url_for('loans.direct_loan'))
            
            # Create loan application record
            application_data = {
                'member_id': member_id,
                'account_number': loan_account['account_number'],
                'loan_amount': str(loan_amount),
                'purpose': purpose,
                'repayment_period_months': repayment_months,
                'interest_rate': str(interest_rate),
                'status': 'disbursed',
                'approved_by': session.get('admin_id'),
                'approved_at': datetime.now().isoformat(),
                'disbursed_at': datetime.now().isoformat(),
                'disbursement_method': disbursement_method,
                'disbursement_reference': reference_number,
                'net_disbursement': str(loan_amount),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            app_response = supabase.table('loan_applications').insert(application_data).execute()
            
            if not app_response.data:
                flash('Failed to create loan record', 'error')
                return redirect(url_for('loans.direct_loan'))
            
            application = app_response.data[0]
            
            # Update loan account balance
            current_balance = Decimal(loan_account.get('current_balance', '0') or '0')
            new_balance = current_balance + loan_amount
            
            supabase.table('loan_accounts')\
                .update({
                    'current_balance': str(new_balance),
                    'available_limit': str(Decimal(loan_account.get('credit_limit', '0') or '0') - new_balance),
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', loan_account['id'])\
                .execute()
            
            # Create repayment schedule
            schedule, monthly_payment, total_repayable = calculate_loan_schedule(
                loan_amount,
                interest_rate,
                repayment_months
            )
            
            # Create repayment schedule in database
            start_date = datetime.now() + timedelta(days=30)
            repayment_data = []
            
            for i, installment in enumerate(schedule):
                due_date = start_date + timedelta(days=30*i)
                
                repayment_data.append({
                    'loan_application_id': application['id'],
                    'member_id': member_id,
                    'installment_number': installment['installment_number'],
                    'due_date': due_date.date().isoformat(),
                    'due_amount': str(installment['due_amount']),
                    'principal_amount': str(installment['principal']),
                    'interest_amount': str(installment['interest']),
                    'status': 'pending',
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                })
            
            if repayment_data:
                supabase.table('loan_repayments').insert(repayment_data).execute()
            
            # Create transaction record
            transaction_data = {
    'loan_account_id': loan_account['id'],  # Changed from member_id
    'transaction_type': 'disbursement',
    'amount': str(loan_amount),
    'balance_before': str(current_balance),
    'balance_after': str(new_balance),
    'reference_number': reference_number,
    'description': f'Direct loan disbursement - {purpose}',
    'payment_method': disbursement_method,
    'processed_by': session.get('admin_id'),
    'created_at': datetime.now().isoformat()
}
            
            supabase.table('loan_transactions').insert(transaction_data).execute()
            
            # Log activity
            log_loan_activity(application['id'], 'direct_loan_issued', 
                             f'Direct loan issued: {loan_amount} to {member["full_name"]}')
            
            flash(f'Direct loan of {loan_amount} issued successfully to {member["full_name"]}', 'success')
            return redirect(url_for('loans.view_application', application_id=application['id']))
            
        except Exception as e:
            print(f"Error issuing direct loan: {e}")
            flash('Error issuing direct loan', 'error')
            return redirect(url_for('loans.direct_loan'))
    
    # GET request - load members for dropdown
    try:
        members_res = supabase.table('members')\
            .select('id, full_name, member_number, email')\
            .order('full_name')\
            .execute()
        
        members = members_res.data if members_res.data else []
        
        # Get loan products for reference
        products_res = supabase.table('loan_products')\
            .select('id, name, interest_rate')\
            .eq('status', 'active')\
            .execute()
        
        products = products_res.data if products_res.data else []
        
        return render_template('admin/loans/direct_loan.html',
                             members=members,
                             products=products)
        
    except Exception as e:
        print(f"Error loading direct loan page: {e}")
        flash('Error loading page', 'error')
        return redirect(url_for('loans.loan_applications'))

# Utility functions
def log_loan_activity(loan_application_id, action, description):
    """Log loan activities"""
    try:
        supabase.table('loan_activity_log').insert({
            'loan_application_id': loan_application_id,
            'action': action,
            'description': description,
            'performed_by': session.get('admin_id'),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'created_at': datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"Failed to log loan activity: {e}")

@loans_bp.route('/add-repayment', methods=['GET', 'POST'])
@admin_login_required
def add_repayment():
    """Add repayment for a member"""
    if request.method == 'POST':
        try:
            # Get form data
            member_id = request.form.get('member_id')
            loan_application_id = request.form.get('loan_application_id')
            amount = Decimal(request.form.get('amount', '0'))
            payment_method = request.form.get('payment_method', '')
            reference_number = request.form.get('reference_number', '')
            remarks = request.form.get('remarks', '')
            
            # Validate
            if not member_id or amount <= 0:
                flash('Invalid member or amount', 'error')
                return redirect(url_for('loans.add_repayment'))
            
            if not payment_method:
                flash('Payment method required', 'error')
                return redirect(url_for('loans.add_repayment'))
            
            # Get member details
            member_res = supabase.table('members').select('*').eq('id', member_id).single().execute()
            if not member_res.data:
                flash('Member not found', 'error')
                return redirect(url_for('loans.add_repayment'))
            
            member = member_res.data
            
            # Get member's loan account
            loan_account_res = supabase.table('loan_accounts')\
                .select('*')\
                .eq('member_id', member_id)\
                .single()\
                .execute()
            
            if not loan_account_res.data:
                flash('Member does not have a loan account', 'error')
                return redirect(url_for('loans.add_repayment'))
            
            loan_account = loan_account_res.data
            
            # If loan application is specified, get details
            loan_application = None
            if loan_application_id:
                app_res = supabase.table('loan_applications')\
                    .select('*')\
                    .eq('id', loan_application_id)\
                    .single()\
                    .execute()
                
                loan_application = app_res.data if app_res.data else None
            
            # Update loan account balance
            current_balance = Decimal(loan_account.get('current_balance', '0') or '0')
            
            if current_balance < amount:
                flash(f'Repayment amount ({amount}) exceeds current balance ({current_balance})', 'error')
                return redirect(url_for('loans.add_repayment'))
            
            new_balance = current_balance - amount
            
            # Update loan account
            supabase.table('loan_accounts')\
                .update({
                    'current_balance': str(new_balance),
                    'available_limit': str(Decimal(loan_account.get('credit_limit', '0') or '0') - new_balance),
                    'updated_at': datetime.now().isoformat()
                })\
                .eq('id', loan_account['id'])\
                .execute()
            
            # Create transaction record - FIXED: using correct column names
            transaction_data = {
                'loan_account_id': loan_account['id'],  # Changed from member_id to loan_account_id
                'transaction_type': 'manual_repayment',
                'amount': str(amount),
                'balance_before': str(current_balance),
                'balance_after': str(new_balance),
                'reference_number': reference_number,
                'description': f'Manual repayment - {remarks}' if remarks else 'Manual loan repayment',
                'payment_method': payment_method,
                'processed_by': session.get('admin_id'),
                'created_at': datetime.now().isoformat()
            }
            
            if loan_application_id:
                transaction_data['loan_application_id'] = loan_application_id
            
            transaction_res = supabase.table('loan_transactions').insert(transaction_data).execute()
            
            if not transaction_res.data:
                flash('Failed to create transaction record', 'error')
                return redirect(url_for('loans.add_repayment'))
            
            # Create repayment record if loan application is specified
            if loan_application_id and loan_application:
                # Find the next installment number
                repayments_res = supabase.table('loan_repayments')\
                    .select('installment_number')\
                    .eq('loan_application_id', loan_application_id)\
                    .order('installment_number', desc=True)\
                    .limit(1)\
                    .execute()
                
                next_installment = 1
                if repayments_res.data:
                    next_installment = repayments_res.data[0]['installment_number'] + 1
                
                # Create repayment record
                repayment_data = {
                    'loan_application_id': loan_application_id,
                    'member_id': member_id,
                    'installment_number': next_installment,
                    'due_date': datetime.now().date().isoformat(),
                    'due_amount': str(amount),
                    'principal_amount': str(amount),  # Assuming full amount goes to principal
                    'interest_amount': '0',
                    'paid_amount': str(amount),
                    'paid_date': datetime.now().date().isoformat(),
                    'payment_method': payment_method,
                    'reference_number': reference_number,
                    'status': 'paid',
                    'remarks': remarks,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                
                supabase.table('loan_repayments').insert(repayment_data).execute()
            
            # Log activity
            log_loan_activity(loan_application_id or 'manual', 'manual_repayment', 
                            f'Manual repayment of {amount} recorded for {member["full_name"]}')
            
            flash(f'Repayment of UGX {amount:,.0f} recorded successfully for {member["full_name"]}', 'success')
            return redirect(url_for('loans.loan_repayments'))
            
        except Exception as e:
            print(f"Error adding repayment: {e}")
            import traceback
            traceback.print_exc()
            flash('Error recording repayment', 'error')
            return redirect(url_for('loans.add_repayment'))
    
    # GET request - load data for the form
    try:
        # Get all members with loan accounts
        members_res = supabase.table('members')\
            .select('id, full_name, member_number, email')\
            .order('full_name')\
            .execute()
        
        members = members_res.data if members_res.data else []
        
        # Get active loan applications
        applications_res = supabase.table('loan_applications')\
            .select('id, account_number, loan_amount, member_id, members(full_name)')\
            .eq('status', 'disbursed')\
            .order('created_at', desc=True)\
            .execute()
        
        applications = applications_res.data if applications_res.data else []
        
        return render_template('admin/loans/add_repayment.html',
                             members=members,
                             applications=applications)
        
    except Exception as e:
        print(f"Error loading add repayment page: {e}")
        flash('Error loading page', 'error')
        return redirect(url_for('loans.loan_repayments'))
        
@loans_bp.route('/get-member-loans/<member_id>')
@admin_login_required
def get_member_loans(member_id):
    """Get member's active loans"""
    try:
        # Get member's loan account
        loan_account_res = supabase.table('loan_accounts')\
            .select('*')\
            .eq('member_id', member_id)\
            .single()\
            .execute()
        
        loan_account = loan_account_res.data if loan_account_res.data else None
        
        # Get active loan applications - FIXED: removed current_balance field
        applications_res = supabase.table('loan_applications')\
            .select('id, account_number, loan_amount, created_at, status')\
            .eq('member_id', member_id)\
            .eq('status', 'disbursed')\
            .order('created_at', desc=True)\
            .execute()
        
        applications = applications_res.data if applications_res.data else []
        
        # Get pending repayments
        pending_repayments_res = supabase.table('loan_repayments')\
            .select('*')\
            .eq('member_id', member_id)\
            .eq('status', 'pending')\
            .order('due_date')\
            .execute()
        
        pending_repayments = pending_repayments_res.data if pending_repayments_res.data else []
        
        # Calculate total pending
        total_pending = sum(Decimal(r.get('due_amount', '0') or '0') for r in pending_repayments)
        
        return jsonify({
            'success': True,
            'loan_account': loan_account,
            'applications': applications,
            'pending_repayments': pending_repayments,
            'total_pending': str(total_pending)
        })
        
    except Exception as e:
        print(f"Error getting member loans: {e}")
        return jsonify({'success': False, 'message': str(e)})
    
    
@loans_bp.route('/accounts')
@admin_login_required
def loan_accounts():
    """View all loan accounts"""
    try:
        # Get query parameters
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        
        # Build query
        query = supabase.table('loan_accounts')\
            .select('*, members(full_name, member_number, email, phone_number)')\
            .order('created_at', desc=True)
        
        if search:
            query = query.or_(f"account_number.ilike.%{search}%,members.full_name.ilike.%{search}%,members.member_number.ilike.%{search}%")
        
        if status:
            query = query.eq('status', status)
        
        response = query.execute()
        accounts = response.data if response.data else []
        
        # Calculate totals
        total_balance = sum(Decimal(acc.get('current_balance', '0') or '0') for acc in accounts)
        total_limit = sum(Decimal(acc.get('credit_limit', '0') or '0') for acc in accounts)
        total_available = sum(Decimal(acc.get('available_limit', '0') or '0') for acc in accounts)
        
        return render_template('admin/loans/accounts.html',
                             accounts=accounts,
                             search=search,
                             status=status,
                             total_balance=total_balance,
                             total_limit=total_limit,
                             total_available=total_available,
                             total_count=len(accounts))
        
    except Exception as e:
        print(f"Error fetching loan accounts: {e}")
        flash('Error loading loan accounts', 'error')
        return render_template(
        'admin/loans/accounts.html',
        accounts=[],
        search='',
        status='',
        total_balance=0,
        total_limit=0,
        total_available=0,
        total_count=0
    )


@loans_bp.route('/accounts/<account_id>')
@admin_login_required
def loan_account_details(account_id):
    """View loan account details"""
    try:
        # Get loan account details
        account_res = supabase.table('loan_accounts')\
            .select('*, members(*)')\
            .eq('id', account_id)\
            .single()\
            .execute()
        
        if not account_res.data:
            flash('Loan account not found', 'error')
            return redirect(url_for('loans.loan_accounts'))
        
        account = account_res.data
        
        # Get loan applications for this account
        applications_res = supabase.table('loan_applications')\
            .select('*')\
            .eq('member_id', account['member_id'])\
            .order('created_at', desc=True)\
            .execute()
        
        applications = applications_res.data if applications_res.data else []
        
        # Get transaction history
        transactions_res = supabase.table('loan_transactions')\
            .select('*')\
            .eq('loan_account_id', account_id)\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        
        # Get repayment history
        repayments_res = supabase.table('loan_repayments')\
            .select('*, loan_applications(account_number)')\
            .eq('member_id', account['member_id'])\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()
        
        repayments = repayments_res.data if repayments_res.data else []
        
        # Get pending repayments
        # Get pending repayments - FIXED QUERY
        pending_res = supabase.table('loan_repayments')\
            .select('*, loan_applications!inner(account_number)') \
            .eq('member_id', account['member_id'])\
            .eq('status', 'pending')\
            .order('due_date')\
            .execute()
        
        pending_repayments = pending_res.data if pending_res.data else []
        print(pending_repayments)
        
        # Calculate totals
        total_pending = sum(Decimal(r.get('due_amount', '0') or '0') for r in pending_repayments)
        
        return render_template('admin/loans/account_details.html',
                             account=account,
                             applications=applications,
                             transactions=transactions,
                             repayments=repayments,
                             pending_repayments=pending_repayments,
                             total_pending=total_pending)
        
    except Exception as e:
        print(f"Error fetching loan account details: {e}")
        flash('Error loading loan account details', 'error')
        return redirect(url_for('loans.loan_accounts'))


@loans_bp.route('/accounts/<account_id>/update-limit', methods=['POST'])
@admin_login_required
def update_credit_limit(account_id):
    """Update credit limit for loan account"""
    try:
        new_limit = Decimal(request.form.get('credit_limit', '0'))
        
        if new_limit <= 0:
            return jsonify({'success': False, 'message': 'Invalid credit limit'}), 400
        
        # Get current account
        account_res = supabase.table('loan_accounts')\
            .select('*')\
            .eq('id', account_id)\
            .single()\
            .execute()
        
        if not account_res.data:
            return jsonify({'success': False, 'message': 'Account not found'}), 404
        
        account = account_res.data
        current_balance = Decimal(account.get('current_balance', '0') or '0')
        
        # Calculate new available limit
        new_available = new_limit - current_balance
        
        # Update account
        supabase.table('loan_accounts')\
            .update({
                'credit_limit': str(new_limit),
                'available_limit': str(new_available),
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', account_id)\
            .execute()
        
        # Log activity
        log_loan_activity(None, 'credit_limit_updated', 
                         f'Credit limit updated from {account.get("credit_limit")} to {new_limit} for account {account.get("account_number")}')
        
        return jsonify({
            'success': True,
            'message': 'Credit limit updated successfully'
        })
        
    except Exception as e:
        print(f"Error updating credit limit: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@loans_bp.route('/accounts/<account_id>/update-status', methods=['POST'])
@admin_login_required
def update_loan_account_status(account_id):
    """Update loan account status"""
    try:
        new_status = request.form.get('status', '')
        
        if new_status not in ['active', 'suspended', 'closed']:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
        # Get current account
        account_res = supabase.table('loan_accounts')\
            .select('*')\
            .eq('id', account_id)\
            .single()\
            .execute()
        
        if not account_res.data:
            return jsonify({'success': False, 'message': 'Account not found'}), 404
        
        account = account_res.data
        
        # If closing account, check if balance is zero
        if new_status == 'closed':
            current_balance = Decimal(account.get('current_balance', '0') or '0')
            if current_balance > 0:
                return jsonify({
                    'success': False, 
                    'message': f'Cannot close account with outstanding balance of {current_balance}'
                }), 400
        
        update_data = {
            'status': new_status,
            'updated_at': datetime.now().isoformat()
        }
        
        if new_status == 'closed':
            update_data['closed_at'] = datetime.now().isoformat()
        
        # Update account
        supabase.table('loan_accounts')\
            .update(update_data)\
            .eq('id', account_id)\
            .execute()
        
        # Log activity
        log_loan_activity(None, 'account_status_updated', 
                         f'Account status changed to {new_status} for account {account.get("account_number")}')
        
        return jsonify({
            'success': True,
            'message': f'Account status updated to {new_status}'
        })
        
    except Exception as e:
        print(f"Error updating account status: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@loans_bp.route('/accounts/create', methods=['GET', 'POST'])
@admin_login_required
def create_loan_account():
    """Create new loan account for member"""
    if request.method == 'POST':
        try:
            member_id = request.form.get('member_id')
            credit_limit = Decimal(request.form.get('credit_limit', '0'))
            interest_rate = Decimal(request.form.get('interest_rate', '0'))
            
            # Validate
            if not member_id:
                flash('Member selection required', 'error')
                return redirect(url_for('loans.create_loan_account'))
            
            if credit_limit <= 0:
                flash('Credit limit must be greater than 0', 'error')
                return redirect(url_for('loans.create_loan_account'))
            
            # Check if member exists
            member_res = supabase.table('members').select('*').eq('id', member_id).single().execute()
            if not member_res.data:
                flash('Member not found', 'error')
                return redirect(url_for('loans.create_loan_account'))
            
            member = member_res.data
            
            # Check if member already has a loan account
            existing_res = supabase.table('loan_accounts')\
                .select('id')\
                .eq('member_id', member_id)\
                .execute()
            
            if existing_res.data:
                flash('Member already has a loan account', 'error')
                return redirect(url_for('loans.create_loan_account'))
            
            # Generate account number
            account_number = f"LA{member.get('member_number', '').replace('MEM', '')}"
            
            # Create loan account
            account_data = {
                'member_id': member_id,
                'account_number': account_number,
                'credit_limit': str(credit_limit),
                'current_balance': '0.00',
                'available_limit': str(credit_limit),
                'interest_rate': str(interest_rate),
                'max_loan_amount': str(credit_limit * Decimal('5')),  # 5x credit limit
                'min_loan_amount': '10000.00',
                'repayment_period_months': 12,
                'status': 'active',
                'credit_score': 700,
                'opened_at': datetime.now().isoformat(),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            response = supabase.table('loan_accounts').insert(account_data).execute()
            
            if not response.data:
                flash('Failed to create loan account', 'error')
                return redirect(url_for('loans.create_loan_account'))
            
            flash(f'Loan account created successfully for {member["full_name"]}', 'success')
            return redirect(url_for('loans.loan_account_details', account_id=response.data[0]['id']))
            
        except Exception as e:
            print(f"Error creating loan account: {e}")
            flash('Error creating loan account', 'error')
            return redirect(url_for('loans.create_loan_account'))
    
    # GET request - load members
    try:
        members_res = supabase.table('members')\
            .select('id, full_name, member_number, email')\
            .order('full_name')\
            .execute()
        
        members = members_res.data if members_res.data else []
        
        # Get members without loan accounts
        members_without_accounts = []
        for member in members:
            account_res = supabase.table('loan_accounts')\
                .select('id')\
                .eq('member_id', member['id'])\
                .execute()
            
            if not account_res.data:
                members_without_accounts.append(member)
        
        return render_template('admin/loans/create_account.html',
                             members=members_without_accounts)
        
    except Exception as e:
        print(f"Error loading create account page: {e}")
        flash('Error loading page', 'error')
        return redirect(url_for('loans.loan_accounts'))