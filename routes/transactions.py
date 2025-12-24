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
expense_incomes_bp = Blueprint('expense_incomes', __name__, url_prefix='/admin/expense_incomes')

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
def generate_expense_number():
    """Generate a unique expense number"""
    try:
        # Get current year and month
        now = datetime.now()
        year = now.strftime('%Y')
        month = now.strftime('%m')
        
        # Get the last expense number for this month/year
        prefix = f"EXP-{year}{month}"
        
        # Query to find the last expense number
        # Wrap this in a try-catch to handle connection issues
        try:
            result = supabase.table('expenses')\
                .select('expense_number')\
                .like('expense_number', f'{prefix}%')\
                .order('expense_number', desc=True)\
                .limit(1)\
                .execute()
            
            if result.data:
                last_number = result.data[0]['expense_number']
                # Extract the numeric part and increment
                last_seq = int(last_number.split('-')[-1])
                new_seq = last_seq + 1
            else:
                new_seq = 1
                
        except Exception as query_error:
            print(f"Error querying for last expense number: {query_error}")
            # Fallback: use timestamp-based number
            timestamp = int(datetime.now().timestamp())
            return f"EXP-{timestamp}"
        
        # Format with leading zeros
        return f"{prefix}-{new_seq:04d}"
        
    except Exception as e:
        print(f"Error generating expense number: {e}")
        # Ultimate fallback
        timestamp = int(datetime.now().timestamp())
        return f"EXP-{timestamp}"
def generate_income_number():
    """Generate a unique income number"""
    try:
        # Get current year and month
        now = datetime.now()
        year = now.strftime('%Y')
        month = now.strftime('%m')
        day = now.strftime('%d')
        
        # Option 1: Year-Month-Day format (like your current pattern)
        prefix = f"INC-{year}{month}{day}"
        
        # Option 2: Year-Month format (like expense pattern)
        # prefix = f"INC-{year}{month}"
        
        # Query to find the last income number
        try:
            result = supabase.table('other_incomes')\
                .select('income_number')\
                .like('income_number', f'{prefix}%')\
                .order('income_number', desc=True)\
                .limit(1)\
                .execute()
            
            if result.data and result.data[0]['income_number']:
                last_number = result.data[0]['income_number']
                # Extract the numeric part and increment
                # Handle different formats: INC-20251223-001 or INC-20251223-1
                parts = last_number.split('-')
                if len(parts) >= 3:
                    try:
                        last_seq = int(parts[-1])
                        new_seq = last_seq + 1
                    except ValueError:
                        # If the last part isn't a number, start from 1
                        new_seq = 1
                else:
                    new_seq = 1
            else:
                new_seq = 1
                
        except Exception as query_error:
            print(f"Error querying for last income number: {query_error}")
            # Fallback 1: Use your existing count-based method
            try:
                count_res = supabase.table('other_incomes')\
                    .select('id', count='exact')\
                    .like('income_number', f'INC-{year}{month}{day}%')\
                    .execute()
                count = count_res.count or 0
                return f'INC-{year}{month}{day}-{str(count + 1).zfill(3)}'
            except Exception:
                # Fallback 2: Use timestamp-based number
                timestamp = int(datetime.now().timestamp())
                return f"INC-{timestamp}"
        
        # Format with leading zeros (3 digits)
        return f"{prefix}-{new_seq:03d}"
        
    except Exception as e:
        print(f"Error generating income number: {e}")
        # Ultimate fallback - timestamp
        timestamp = int(datetime.now().timestamp())
        return f"INC-{timestamp}"
    
def calculate_daily_profit(start_date=None, end_date=None):
    """Calculate profit for a given date range"""
    try:
        # Use today as default if no dates provided
        if not start_date:
            start_date = datetime.now().date()
        if not end_date:
            end_date = datetime.now().date()
        
        print(f"=== DEBUG calculate_daily_profit() ===")
        print(f"Date range: {start_date.isoformat()} to {end_date.isoformat()}")
        
        # Calculate total member income for date range
        print("\n1. Fetching member incomes...")
        member_income_res = supabase.table('member_incomes')\
            .select('amount')\
            .gte('payment_date', start_date.isoformat())\
            .lte('payment_date', end_date.isoformat())\
            .execute()
        
        print(f"Member income count: {len(member_income_res.data) if member_income_res.data else 0}")
        total_member_income = sum(Decimal(r['amount']) for r in member_income_res.data) if member_income_res.data else Decimal('0')
        print(f"Total member income: {total_member_income}")
        
        # Calculate total other income for date range
        print("\n2. Fetching other incomes...")
        other_income_res = supabase.table('other_incomes')\
            .select('amount')\
            .gte('payment_date', start_date.isoformat())\
            .lte('payment_date', end_date.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        print(f"Other income count: {len(other_income_res.data) if other_income_res.data else 0}")
        total_other_income = sum(Decimal(r['amount']) for r in other_income_res.data) if other_income_res.data else Decimal('0')
        print(f"Total other income: {total_other_income}")
        
        # Calculate income from ALL share transactions for date range (purchase is income for SACCO)
        print("\n3. Fetching ALL share transactions...")
        shares_income_res = supabase.table('share_transactions')\
            .select('total_amount, transaction_type, transaction_date')\
            .gte('transaction_date', f'{start_date.isoformat()}T00:00:00')\
            .lte('transaction_date', f'{end_date.isoformat()}T23:59:59')\
            .execute()
        
        print(f"Share transactions count: {len(shares_income_res.data) if shares_income_res.data else 0}")
        
        # Calculate both purchase and sale income
        total_shares_purchase = Decimal('0')
        total_shares_sale = Decimal('0')
        
        if shares_income_res.data:
            for trans in shares_income_res.data:
                amount = Decimal(str(trans['total_amount'])) if trans['total_amount'] else Decimal('0')
                trans_type = trans['transaction_type']
                
                if trans_type == 'purchase':
                    total_shares_purchase += amount
                elif trans_type == 'sale':
                    total_shares_sale += amount
            
            print(f"  - Purchase transactions: {total_shares_purchase}")
            print(f"  - Sale transactions: {total_shares_sale}")
        
        total_shares_income = total_shares_purchase + total_shares_sale
        print(f"Total shares income (purchase + sale): {total_shares_income}")
        
        # Calculate income from loan interest for date range
        print("\n4. Fetching loan repayments/interest...")
        loan_interest_res = supabase.table('loan_repayments')\
            .select('interest_amount, paid_date, status')\
            .gte('paid_date', start_date.isoformat())\
            .lte('paid_date', end_date.isoformat())\
            .eq('status', 'paid')\
            .execute()
        
        print(f"Loan repayments count: {len(loan_interest_res.data) if loan_interest_res.data else 0}")
        
        total_loan_interest = Decimal('0')
        if loan_interest_res.data:
            for repay in loan_interest_res.data:
                interest = Decimal(str(repay['interest_amount'])) if repay['interest_amount'] else Decimal('0')
                total_loan_interest += interest
                print(f"  - Interest: {interest}, Date: {repay['paid_date']}")
        
        print(f"Total loan interest: {total_loan_interest}")
        
        # Calculate total expenses for date range
        print("\n5. Fetching expenses...")
        expenses_res = supabase.table('expenses')\
            .select('amount, payment_date, status')\
            .gte('payment_date', start_date.isoformat())\
            .lte('payment_date', end_date.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        print(f"Expenses count: {len(expenses_res.data) if expenses_res.data else 0}")
        total_expenses = sum(Decimal(r['amount']) for r in expenses_res.data) if expenses_res.data else Decimal('0')
        print(f"Total expenses: {total_expenses}")
        
        # Calculate net profit
        net_profit = (total_member_income + total_other_income + total_shares_income + total_loan_interest) - total_expenses
        
        print("\n=== FINAL CALCULATIONS ===")
        print(f"Total Member Income: {total_member_income}")
        print(f"Total Other Income: {total_other_income}")
        print(f"Total Shares Income: {total_shares_income}")
        print(f"Total Loan Interest: {total_loan_interest}")
        print(f"Total Expenses: {total_expenses}")
        print(f"Net Profit: {net_profit}")
        print("=== END DEBUG ===\n")
        
        return {
            'total_member_income': total_member_income,
            'total_other_income': total_other_income,
            'total_shares_income': total_shares_income,
            'total_loan_interest': total_loan_interest,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
            'start_date': start_date,
            'end_date': end_date
        }
        
    except Exception as e:
        print(f"ERROR in calculate_daily_profit(): {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
        # Return default values on error
        return {
            'total_member_income': Decimal('0'),
            'total_other_income': Decimal('0'),
            'total_shares_income': Decimal('0'),
            'total_loan_interest': Decimal('0'),
            'total_expenses': Decimal('0'),
            'net_profit': Decimal('0'),
            'start_date': start_date or datetime.now().date(),
            'end_date': end_date or datetime.now().date()
        }
        
def calculate_financial_report(start_date, end_date):
    """Calculate financial report data for any date range"""
    try:
        print(f"=== DEBUG calculate_financial_report() ===")
        print(f"Date range: {start_date.isoformat()} to {end_date.isoformat()}")
        
        # Calculate total member income for date range
        print("\n1. Fetching member incomes...")
        member_income_res = supabase.table('member_incomes')\
            .select('amount, income_type, payment_date')\
            .gte('payment_date', start_date.isoformat())\
            .lte('payment_date', end_date.isoformat())\
            .execute()
        
        print(f"Member income count: {len(member_income_res.data) if member_income_res.data else 0}")
        total_member_income = Decimal('0')
        member_income_by_type = {}
        
        if member_income_res.data:
            for income in member_income_res.data:
                amount = Decimal(str(income['amount'])) if income['amount'] else Decimal('0')
                income_type = income['income_type'] or 'other'
                total_member_income += amount
                
                # Group by income type
                if income_type in member_income_by_type:
                    member_income_by_type[income_type] += amount
                else:
                    member_income_by_type[income_type] = amount
        
        print(f"Total member income: {total_member_income}")
        print(f"Member income by type: {member_income_by_type}")
        
        # Calculate total other income for date range
        print("\n2. Fetching other incomes...")
        other_income_res = supabase.table('other_incomes')\
            .select('amount, income_categories(name), payment_date')\
            .gte('payment_date', start_date.isoformat())\
            .lte('payment_date', end_date.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        print(f"Other income count: {len(other_income_res.data) if other_income_res.data else 0}")
        total_other_income = Decimal('0')
        other_income_by_category = {}
        
        if other_income_res.data:
            for income in other_income_res.data:
                amount = Decimal(str(income['amount'])) if income['amount'] else Decimal('0')
                total_other_income += amount
                
                # Group by category
                category_name = 'Unknown'
                if income.get('income_categories'):
                    category_name = income['income_categories'].get('name', 'Unknown')
                else:
                    # Try to get category name from category table if not joined
                    try:
                        cat_res = supabase.table('income_categories')\
                            .select('name')\
                            .eq('id', income.get('category_id'))\
                            .single()\
                            .execute()
                        if cat_res.data:
                            category_name = cat_res.data['name']
                    except:
                        pass
                
                if category_name in other_income_by_category:
                    other_income_by_category[category_name] += amount
                else:
                    other_income_by_category[category_name] = amount
        
        print(f"Total other income: {total_other_income}")
        print(f"Other income by category: {other_income_by_category}")
        
        # Calculate income from ALL share transactions for date range
        print("\n3. Fetching share transactions...")
        shares_income_res = supabase.table('share_transactions')\
            .select('total_amount, transaction_type, transaction_date, payment_method')\
            .gte('transaction_date', f'{start_date.isoformat()}T00:00:00')\
            .lte('transaction_date', f'{end_date.isoformat()}T23:59:59')\
            .execute()
        
        print(f"Share transactions count: {len(shares_income_res.data) if shares_income_res.data else 0}")
        
        total_shares_purchase = Decimal('0')
        total_shares_sale = Decimal('0')
        share_transactions_by_type = {'purchase': Decimal('0'), 'sale': Decimal('0')}
        
        if shares_income_res.data:
            for trans in shares_income_res.data:
                amount = Decimal(str(trans['total_amount'])) if trans['total_amount'] else Decimal('0')
                trans_type = trans.get('transaction_type', 'purchase')
                
                if trans_type == 'purchase':
                    total_shares_purchase += amount
                    share_transactions_by_type['purchase'] += amount
                elif trans_type == 'sale':
                    total_shares_sale += amount
                    share_transactions_by_type['sale'] += amount
            
            print(f"  - Purchase transactions: {total_shares_purchase}")
            print(f"  - Sale transactions: {total_shares_sale}")
        
        total_shares_income = total_shares_purchase + total_shares_sale
        print(f"Total shares income: {total_shares_income}")
        
        # Calculate income from loan interest for date range
        print("\n4. Fetching loan repayments/interest...")
        loan_interest_res = supabase.table('loan_repayments')\
            .select('interest_amount, principal_amount, paid_date, status, payment_method, reference_number')\
            .gte('paid_date', start_date.isoformat())\
            .lte('paid_date', end_date.isoformat())\
            .eq('status', 'paid')\
            .execute()
        
        print(f"Loan repayments count: {len(loan_interest_res.data) if loan_interest_res.data else 0}")
        
        total_loan_interest = Decimal('0')
        total_loan_principal = Decimal('0')
        
        if loan_interest_res.data:
            for repay in loan_interest_res.data:
                interest = Decimal(str(repay['interest_amount'])) if repay['interest_amount'] else Decimal('0')
                principal = Decimal(str(repay['principal_amount'])) if repay['principal_amount'] else Decimal('0')
                total_loan_interest += interest
                total_loan_principal += principal
        
        print(f"Total loan interest: {total_loan_interest}")
        print(f"Total loan principal: {total_loan_principal}")
        
        # Calculate total expenses for date range
        print("\n5. Fetching expenses...")
        expenses_res = supabase.table('expenses')\
            .select('amount, expense_categories(name), payment_date, payment_method, description')\
            .gte('payment_date', start_date.isoformat())\
            .lte('payment_date', end_date.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        print(f"Expenses count: {len(expenses_res.data) if expenses_res.data else 0}")
        
        total_expenses = Decimal('0')
        expenses_by_category = {}
        expenses_list = []
        
        if expenses_res.data:
            for expense in expenses_res.data:
                amount = Decimal(str(expense['amount'])) if expense['amount'] else Decimal('0')
                total_expenses += amount
                
                # Group by category
                category_name = 'Unknown'
                if expense.get('expense_categories'):
                    category_name = expense['expense_categories'].get('name', 'Unknown')
                else:
                    # Try to get category name from category table if not joined
                    try:
                        cat_res = supabase.table('expense_categories')\
                            .select('name')\
                            .eq('id', expense.get('category_id'))\
                            .single()\
                            .execute()
                        if cat_res.data:
                            category_name = cat_res.data['name']
                    except:
                        pass
                
                if category_name in expenses_by_category:
                    expenses_by_category[category_name] += amount
                else:
                    expenses_by_category[category_name] = amount
                
                # Store expense details for detailed report
                expenses_list.append({
                    'date': expense['payment_date'],
                    'category': category_name,
                    'amount': amount,
                    'description': expense.get('description', ''),
                    'payment_method': expense.get('payment_method', '')
                })
        
        print(f"Total expenses: {total_expenses}")
        print(f"Expenses by category: {expenses_by_category}")
        
        # Calculate net profit
        total_income = total_member_income + total_other_income + total_shares_income + total_loan_interest
        net_profit = total_income - total_expenses
        
        print("\n=== FINAL CALCULATIONS ===")
        print(f"Total Member Income: {total_member_income}")
        print(f"Total Other Income: {total_other_income}")
        print(f"Total Shares Income: {total_shares_income}")
        print(f"Total Loan Interest: {total_loan_interest}")
        print(f"Total Income: {total_income}")
        print(f"Total Expenses: {total_expenses}")
        print(f"Net Profit: {net_profit}")
        print("=== END DEBUG ===\n")
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_member_income': total_member_income,
            'total_other_income': total_other_income,
            'total_shares_income': total_shares_income,
            'total_loan_interest': total_loan_interest,
            'total_expenses': total_expenses,
            'net_profit': net_profit,
            'member_income_by_type': member_income_by_type,
            'other_income_by_category': other_income_by_category,
            'expenses_by_category': expenses_by_category,
            'share_transactions_by_type': share_transactions_by_type,
            'total_loan_principal': total_loan_principal,
            'expenses_list': expenses_list[:20],  # Limit to first 20 for performance
            'total_income': total_income
        }
        
    except Exception as e:
        print(f"ERROR in calculate_financial_report(): {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
        # Return default values on error
        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_member_income': Decimal('0'),
            'total_other_income': Decimal('0'),
            'total_shares_income': Decimal('0'),
            'total_loan_interest': Decimal('0'),
            'total_expenses': Decimal('0'),
            'net_profit': Decimal('0'),
            'member_income_by_type': {},
            'other_income_by_category': {},
            'expenses_by_category': {},
            'share_transactions_by_type': {'purchase': Decimal('0'), 'sale': Decimal('0')},
            'total_loan_principal': Decimal('0'),
            'expenses_list': [],
            'total_income': Decimal('0')
        }
        
               
def ensure_income_categories():
    """Ensure required income categories exist"""
    try:
        # Default income categories including shares and loan interest
        default_categories = [
            {
                'name': 'Interest on Loans',
                'description': 'Income from loan interest payments',
                'type': 'loan_interest',
                'status': 'active'
            },
            {
                'name': 'Sale of Shares',
                'description': 'Income from selling SACCO shares',
                'type': 'shares_sale',
                'status': 'active'
            },
            {
                'name': 'Membership Fees',
                'description': 'Income from membership registration and renewal fees',
                'type': 'membership',
                'status': 'active'
            },
            {
                'name': 'Penalty Fees',
                'description': 'Income from late payment penalties and fines',
                'type': 'penalty',
                'status': 'active'
            },
            {
                'name': 'Donations',
                'description': 'Donations and grants received',
                'type': 'donation',
                'status': 'active'
            },
            {
                'name': 'Investment Income',
                'description': 'Income from investments and dividends',
                'type': 'investment',
                'status': 'active'
            },
            {
                'name': 'Other Income',
                'description': 'Miscellaneous income sources',
                'type': 'other',
                'status': 'active'
            }
        ]
        
        for category in default_categories:
            # Check if category exists
            existing_res = supabase.table('income_categories')\
                .select('id')\
                .eq('name', category['name'])\
                .execute()
            
            if not existing_res.data:
                # Insert new category
                category.update({
                    'created_by': None,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                })
                
                supabase.table('income_categories').insert(category).execute()
                print(f"Created income category: {category['name']}")
        
    except Exception as e:
        print(f"Error ensuring income categories: {e}")

# Routes
@expense_incomes_bp.route('/')
@admin_login_required
def dashboard():
    """Expense and Income Dashboard with date range filtering"""
    try:
        print("\n=== DEBUG dashboard() ===")
        
        # Get date filter parameters
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')
        
        # Parse dates or use defaults
        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            else:
                # Default to beginning of current month
                start_date = datetime.now().replace(day=1).date()
            
            if end_date_str:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            else:
                # Default to today
                end_date = datetime.now().date()
                
        except ValueError:
            # If date parsing fails, use defaults
            start_date = datetime.now().replace(day=1).date()
            end_date = datetime.now().date()
        
        print(f"Date filter: {start_date.isoformat()} to {end_date.isoformat()}")
        
        # Get profit calculation for the date range
        profit_data = calculate_daily_profit(start_date, end_date)
        print(f"Profit data: {profit_data}")
        
        # Get recent transactions (without date filter for recent)
        print("\nFetching recent expenses...")
        recent_expenses = supabase.table('expenses')\
            .select('*, expense_categories(name)')\
            .order('created_at', desc=True)\
            .limit(5)\
            .execute()
        
        print(f"Recent expenses count: {len(recent_expenses.data) if recent_expenses.data else 0}")
        
        print("\nFetching recent incomes...")
        recent_incomes = supabase.table('other_incomes')\
            .select('*, income_categories(name)')\
            .order('created_at', desc=True)\
            .limit(5)\
            .execute()
        
        print(f"Recent incomes count: {len(recent_incomes.data) if recent_incomes.data else 0}")
        
        # Get monthly summary for the filtered date range
        monthly_expenses_res = supabase.table('expenses')\
            .select('amount')\
            .gte('payment_date', start_date.isoformat())\
            .lte('payment_date', end_date.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        monthly_incomes_res = supabase.table('other_incomes')\
            .select('amount')\
            .gte('payment_date', start_date.isoformat())\
            .lte('payment_date', end_date.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        monthly_expenses = sum(Decimal(r['amount']) for r in monthly_expenses_res.data) if monthly_expenses_res.data else Decimal('0')
        monthly_incomes = sum(Decimal(r['amount']) for r in monthly_incomes_res.data) if monthly_incomes_res.data else Decimal('0')
        
        print(f"Monthly expenses ({start_date} to {end_date}): {monthly_expenses}")
        print(f"Monthly incomes ({start_date} to {end_date}): {monthly_incomes}")
        print("=== END dashboard() DEBUG ===\n")
        
        return render_template('admin/expense_incomes/dashboard.html',
                             profit_data=profit_data,
                             recent_expenses=recent_expenses.data if recent_expenses.data else [],
                             recent_incomes=recent_incomes.data if recent_incomes.data else [],
                             monthly_expenses=monthly_expenses,
                             monthly_incomes=monthly_incomes,
                             start_date=start_date_str,
                             end_date=end_date_str)
        
    except Exception as e:
        print(f"ERROR in dashboard(): {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
        flash('Error loading dashboard', 'error')
        # Provide default profit data structure
        default_profit_data = {
            'total_member_income': Decimal('0'),
            'total_other_income': Decimal('0'),
            'total_shares_income': Decimal('0'),
            'total_loan_interest': Decimal('0'),
            'total_expenses': Decimal('0'),
            'net_profit': Decimal('0'),
            'start_date': datetime.now().replace(day=1).date(),
            'end_date': datetime.now().date()
        }
        return render_template('admin/expense_incomes/dashboard.html',
                             profit_data=default_profit_data,
                             recent_expenses=[],
                             recent_incomes=[],
                             monthly_expenses=Decimal('0'),
                             monthly_incomes=Decimal('0'),
                             start_date='',
                             end_date='')
        
        
# Expense Categories Management
@expense_incomes_bp.route('/expense-categories')
@admin_login_required
def expense_categories():
    """Manage expense categories"""
    try:
        categories_res = supabase.table('expense_categories')\
            .select('*')\
            .order('name')\
            .execute()
        
        categories = categories_res.data if categories_res.data else []
        
        return render_template('admin/expense_incomes/expense_categories.html',
                             categories=categories)
        
    except Exception as e:
        print(f"Error loading expense categories: {e}")
        flash('Error loading expense categories', 'error')
        return render_template('admin/expense_incomes/expense_categories.html', categories=[])
    
    
@expense_incomes_bp.route('/expense-categories/add', methods=['POST'])
@admin_login_required
def add_expense_category():
    """Add new expense category"""
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            return jsonify({
                'success': False,
                'message': 'Category name is required'
            }), 400

        # Normalize name to avoid duplicates (Transport vs transport)
        normalized_name = name.lower()

        # Check if category already exists
        existing_res = (
            supabase.table('expense_categories')
            .select('id')
            .ilike('name', normalized_name)
            .limit(1)
            .execute()
        )

        if existing_res.data:
            return jsonify({
                'success': False,
                'message': 'Category already exists'
            }), 400

        now = datetime.utcnow().isoformat()

        category_data = {
            'name': name,
            'description': description or None,
            'created_by': session.get('admin_id'),
            'created_at': now,
            'updated_at': now
        }

        insert_res = (
            supabase.table('expense_categories')
            .insert(category_data)
            .execute()
        )

        if not insert_res.data:
            raise Exception("Failed to insert expense category")

        return jsonify({
            'success': True,
            'message': 'Category added successfully',
            'category': insert_res.data[0]
        })

    except Exception as e:
        print(f"[EXPENSE CATEGORY ERROR]: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to add expense category'
        }), 500

@expense_incomes_bp.route('/expense-categories/edit/<category_id>', methods=['POST'])
@admin_login_required
def edit_expense_category(category_id):
    """Edit expense category"""
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        status = request.form.get('status', 'active')
        
        if not name:
            return jsonify({'success': False, 'message': 'Category name is required'}), 400
        
        # Check if category exists
        existing_res = supabase.table('expense_categories')\
            .select('id')\
            .eq('id', category_id)\
            .execute()
        
        if not existing_res.data:
            return jsonify({'success': False, 'message': 'Category not found'}), 404
        
        # Update category
        update_data = {
            'name': name,
            'description': description,
            'status': status,
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('expense_categories').update(update_data).eq('id', category_id).execute()
        
        return jsonify({'success': True, 'message': 'Category updated successfully'})
        
    except Exception as e:
        print(f"Error editing expense category: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Income Categories Management
@expense_incomes_bp.route('/income-categories')
@admin_login_required
def income_categories():
    """Manage income categories"""
    try:
        categories_res = supabase.table('income_categories')\
            .select('*')\
            .order('name')\
            .execute()
        
        categories = categories_res.data if categories_res.data else []
        
        return render_template('admin/expense_incomes/income_categories.html',
                             categories=categories)
        
    except Exception as e:
        print(f"Error loading income categories: {e}")
        flash('Error loading income categories', 'error')
        return render_template('admin/expense_incomes/income_categories.html', categories=[])

@expense_incomes_bp.route('/income-categories/add', methods=['POST'])
@admin_login_required
def add_income_category():
    """Add new income category"""
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        category_type = request.form.get('type', 'other')
        
        if not name:
            return jsonify({'success': False, 'message': 'Category name is required'}), 400
        
        # Check if category already exists
        existing_res = supabase.table('income_categories')\
            .select('id')\
            .eq('name', name)\
            .execute()
        
        if existing_res.data:
            return jsonify({'success': False, 'message': 'Category already exists'}), 400
        
        # Insert new category
        category_data = {
            'name': name,
            'description': description,
            'type': category_type,
            'created_by': session.get('admin_id'),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('income_categories').insert(category_data).execute()
        
        return jsonify({'success': True, 'message': 'Category added successfully'})
        
    except Exception as e:
        print(f"Error adding income category: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Expenses Management
@expense_incomes_bp.route('/expenses')
@admin_login_required
def expenses_list():
    """List all expenses"""
    try:
        # Get query parameters
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        category_id = request.args.get('category_id', '')
        status = request.args.get('status', '')
        
        # Build query
        query = supabase.table('expenses')\
            .select('*, expense_categories(name)')\
            .order('payment_date', desc=True)\
            .order('created_at', desc=True)
        
        if start_date:
            query = query.gte('payment_date', start_date)
        if end_date:
            query = query.lte('payment_date', end_date)
        if category_id:
            query = query.eq('category_id', category_id)
        if status:
            query = query.eq('status', status)
        
        expenses_res = query.execute()
        expenses = expenses_res.data if expenses_res.data else []
        
        # Get expense categories for filter
        categories_res = supabase.table('expense_categories')\
            .select('id, name')\
            .eq('status', 'active')\
            .execute()
        
        categories = categories_res.data if categories_res.data else []
        
        # Calculate totals
        total_amount = sum(Decimal(e['amount']) for e in expenses)
        
        return render_template('admin/expense_incomes/expenses.html',
                             expenses=expenses,
                             categories=categories,
                             start_date=start_date,
                             end_date=end_date,
                             category_id=category_id,
                             status=status,
                             total_amount=total_amount)
        
    except Exception as e:
        print(f"Error loading expenses: {e}")
        flash('Error loading expenses', 'error')
        return render_template('admin/expense_incomes/expenses.html', expenses=[])
    
    
@expense_incomes_bp.route('/expenses/add', methods=['GET', 'POST'])
@admin_login_required
def add_expense():
    """Add new expense"""
    # Load categories first (for both GET and POST to show them after error)
    try:
        categories_res = supabase.table('expense_categories')\
            .select('id, name')\
            .eq('status', 'active')\
            .order('name')\
            .execute()
        categories = categories_res.data if categories_res.data else []
    except Exception as e:
        print(f"Error loading categories: {e}")
        flash('Error loading expense categories. Please try again.', 'error')
        categories = []
    
    if request.method == 'POST':
        try:
            category_id = request.form.get('category_id')
            amount = Decimal(request.form.get('amount', '0'))
            description = request.form.get('description', '').strip()
            payment_method = request.form.get('payment_method', '')
            reference_number = request.form.get('reference_number', '').strip()
            payment_date = request.form.get('payment_date', '')
            paid_to = request.form.get('paid_to', '').strip()
            notes = request.form.get('notes', '').strip()
            
            # Validate
            validation_errors = []
            if not category_id or amount <= 0:
                validation_errors.append('Invalid category or amount')
            if not payment_method:
                validation_errors.append('Payment method required')
            if not payment_date:
                validation_errors.append('Payment date required')
            
            if validation_errors:
                for error in validation_errors:
                    flash(error, 'error')
                return render_template('admin/expense_incomes/add_expense.html',
                                     categories=categories)
            
            # Generate expense number (with error handling)
            try:
                expense_number = generate_expense_number()
            except Exception as e:
                print(f"Error generating expense number: {e}")
                # Use a simple timestamp-based number as fallback
                import time
                expense_number = f"EXP-{int(time.time())}"
            
            # Create expense record
            expense_data = {
                'expense_number': expense_number,
                'category_id': category_id,
                'amount': float(amount),
                'description': description,
                'payment_method': payment_method,
                'reference_number': reference_number if reference_number else None,
                'payment_date': payment_date,
                'paid_to': paid_to if paid_to else None,
                'approved_by': session.get('admin_id'),
                'status': 'approved',
                'notes': notes if notes else None,
                'created_by': session.get('admin_id'),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Debug: Print what we're sending
            print(f"Attempting to insert expense: {expense_data}")
            
            # Try to insert with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = supabase.table('expenses').insert(expense_data).execute()
                    print(f"Expense inserted successfully: {response}")
                    break
                except Exception as insert_error:
                    if attempt == max_retries - 1:
                        raise insert_error
                    print(f"Insert attempt {attempt + 1} failed, retrying...: {insert_error}")
                    import time
                    time.sleep(1)  # Wait 1 second before retry
            
            flash(f'Expense of UGX {amount:,.0f} recorded successfully', 'success')
            return redirect(url_for('expense_incomes.expenses_list'))
            
        except Exception as e:
            print(f"Error adding expense: {type(e).__name__}: {str(e)}")
            # Print full traceback for debugging
            import traceback
            traceback.print_exc()
            
            # Provide user-friendly error message
            error_msg = str(e)
            if "Cloudflare" in error_msg or "Worker threw exception" in error_msg:
                error_msg = "Cannot connect to database. Please check your internet connection or try again later."
            
            flash(f'Error recording expense: {error_msg}', 'error')
            return render_template('admin/expense_incomes/add_expense.html',
                                 categories=categories)
    
    # GET request - load form
    return render_template('admin/expense_incomes/add_expense.html',
                         categories=categories)
        
# Other Incomes Management
@expense_incomes_bp.route('/other-incomes')
@admin_login_required
def other_incomes_list():
    """List all other incomes"""
    try:
        # Get query parameters
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        category_id = request.args.get('category_id', '')
        
        # Build query
        query = supabase.table('other_incomes')\
            .select('*, income_categories(name, type)')\
            .order('payment_date', desc=True)\
            .order('created_at', desc=True)
        
        if start_date:
            query = query.gte('payment_date', start_date)
        if end_date:
            query = query.lte('payment_date', end_date)
        if category_id:
            query = query.eq('category_id', category_id)
        
        incomes_res = query.execute()
        incomes = incomes_res.data if incomes_res.data else []
        
        # Get income categories for filter
        categories_res = supabase.table('income_categories')\
            .select('id, name')\
            .eq('status', 'active')\
            .execute()
        
        categories = categories_res.data if categories_res.data else []
        
        # Calculate totals
        total_amount = sum(Decimal(i['amount']) for i in incomes)
        
        return render_template('admin/expense_incomes/other_incomes.html',
                             incomes=incomes,
                             categories=categories,
                             start_date=start_date,
                             end_date=end_date,
                             category_id=category_id,
                             total_amount=total_amount)
        
    except Exception as e:
        print(f"Error loading other incomes: {e}")
        flash('Error loading other incomes', 'error')
        return render_template('admin/expense_incomes/other_incomes.html', incomes=[])

@expense_incomes_bp.route('/other-incomes/add', methods=['GET', 'POST'])
@admin_login_required
def add_other_income():
    """Add new other income"""
    if request.method == 'POST':
        try:
            category_id = request.form.get('category_id')
            amount = Decimal(request.form.get('amount', '0'))
            description = request.form.get('description', '').strip()
            payment_method = request.form.get('payment_method', '')
            reference_number = request.form.get('reference_number', '').strip()
            payment_date = request.form.get('payment_date', '')
            received_from = request.form.get('received_from', '').strip()
            notes = request.form.get('notes', '').strip()
            
            # Validate
            if not category_id or amount <= 0:
                flash('Invalid category or amount', 'error')
                return redirect(url_for('expense_incomes.add_other_income'))
            
            if not payment_method:
                flash('Payment method required', 'error')
                return redirect(url_for('expense_incomes.add_other_income'))
            
            if not payment_date:
                flash('Payment date required', 'error')
                return redirect(url_for('expense_incomes.add_other_income'))
            
            # Generate income number
            income_number = generate_income_number()
            
            # Create income record
            income_data = {
                'income_number': income_number,
                'category_id': category_id,
                'amount': str(amount),
                'description': description,
                'payment_method': payment_method,
                'reference_number': reference_number,
                'payment_date': payment_date,
                'received_from': received_from,
                'status': 'approved',
                'notes': notes,
                'created_by': session.get('admin_id'),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            supabase.table('other_incomes').insert(income_data).execute()
            
            flash(f'Income of UGX {amount:,.0f} recorded successfully', 'success')
            return redirect(url_for('expense_incomes.other_incomes_list'))
            
        except Exception as e:
            print(f"Error adding other income: {e}")
            flash('Error recording income', 'error')
            return redirect(url_for('expense_incomes.add_other_income'))
    
    # GET request - load form data
    try:
        categories_res = supabase.table('income_categories')\
            .select('id, name, type')\
            .eq('status', 'active')\
            .order('name')\
            .execute()
        
        categories = categories_res.data if categories_res.data else []
        
        return render_template('admin/expense_incomes/add_other_income.html',
                             categories=categories)
        
    except Exception as e:
        print(f"Error loading add income page: {e}")
        flash('Error loading page', 'error')
        return redirect(url_for('expense_incomes.other_incomes_list'))

# Member Incomes
@expense_incomes_bp.route('/member-incomes')
@admin_login_required
def member_incomes_list():
    """List member incomes"""
    try:
        # Get query parameters
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        income_type = request.args.get('income_type', '')
        
        # Build query
        query = supabase.table('member_incomes')\
            .select('*, members(full_name, member_number)')\
            .order('payment_date', desc=True)\
            .order('created_at', desc=True)
        
        if start_date:
            query = query.gte('payment_date', start_date)
        if end_date:
            query = query.lte('payment_date', end_date)
        if income_type:
            query = query.eq('income_type', income_type)
        
        incomes_res = query.execute()
        incomes = incomes_res.data if incomes_res.data else []
        
        # Calculate totals by type
        totals_by_type = {}
        for income in incomes:
            income_type = income['income_type']
            amount = Decimal(income['amount'])
            totals_by_type[income_type] = totals_by_type.get(income_type, Decimal('0')) + amount
        
        # Total amount
        total_amount = sum(Decimal(i['amount']) for i in incomes)
        
        return render_template('admin/expense_incomes/member_incomes.html',
                             incomes=incomes,
                             start_date=start_date,
                             end_date=end_date,
                             income_type=income_type,
                             totals_by_type=totals_by_type,
                             total_amount=total_amount)
        
    except Exception as e:
        print(f"Error loading member incomes: {e}")
        flash('Error loading member incomes', 'error')
        return render_template('admin/expense_incomes/member_incomes.html', incomes=[])

@expense_incomes_bp.route('/record-member-income', methods=['POST'])
@admin_login_required
def record_member_income():
    """Record income from a member"""
    try:
        member_id = request.form.get('member_id')
        income_type = request.form.get('income_type')
        amount = Decimal(request.form.get('amount', '0'))
        description = request.form.get('description', '').strip()
        reference_id = request.form.get('reference_id', '').strip()
        payment_date = request.form.get('payment_date', datetime.now().date().isoformat())
        
        # Validate
        if not member_id or amount <= 0:
            return jsonify({'success': False, 'message': 'Invalid member or amount'}), 400
        
        if not income_type:
            return jsonify({'success': False, 'message': 'Income type required'}), 400
        
        # Check if member exists
        member_res = supabase.table('members').select('id').eq('id', member_id).single().execute()
        if not member_res.data:
            return jsonify({'success': False, 'message': 'Member not found'}), 404
        
        # Create member income record
        income_data = {
            'member_id': member_id,
            'income_type': income_type,
            'amount': str(amount),
            'description': description,
            'reference_id': reference_id,
            'payment_date': payment_date,
            'recorded_by': session.get('admin_id'),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('member_incomes').insert(income_data).execute()
        
        return jsonify({'success': True, 'message': f'Income of UGX {amount:,.0f} recorded successfully'})
        
    except Exception as e:
        print(f"Error recording member income: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Financial Reports
@expense_incomes_bp.route('/reports')
@admin_login_required
def financial_reports():
    """View financial reports with date range filtering"""
    try:
        # Get query parameters
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')
        
        # Parse dates or use defaults
        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            else:
                # Default to beginning of current month
                start_date = datetime.now().replace(day=1).date()
            
            if end_date_str:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            else:
                # Default to today
                end_date = datetime.now().date()
                
        except ValueError:
            # If date parsing fails, use defaults
            start_date = datetime.now().replace(day=1).date()
            end_date = datetime.now().date()
        
        # Calculate report data for the date range
        report_data = calculate_financial_report(start_date, end_date)
        
        # Get years for filter dropdown (for backward compatibility if needed)
        years = list(range(datetime.now().year - 5, datetime.now().year + 1))
        
        return render_template('admin/expense_incomes/reports.html',
                             report_data=report_data,
                             start_date=start_date_str,
                             end_date=end_date_str,
                             years=years)
        
    except Exception as e:
        print(f"Error generating financial report: {e}")
        flash('Error generating financial report', 'error')
        
        # Provide default report data
        default_report_data = {
            'start_date': datetime.now().replace(day=1).date(),
            'end_date': datetime.now().date(),
            'total_member_income': Decimal('0'),
            'total_other_income': Decimal('0'),
            'total_shares_income': Decimal('0'),
            'total_loan_interest': Decimal('0'),
            'total_expenses': Decimal('0'),
            'net_profit': Decimal('0'),
            'member_income_by_type': {},
            'other_income_by_category': {},
            'expenses_by_category': {},
            'share_transactions_by_type': {'purchase': Decimal('0'), 'sale': Decimal('0')},
            'total_loan_principal': Decimal('0'),
            'expenses_list': [],
            'total_income': Decimal('0')
        }
        
        return render_template('admin/expense_incomes/reports.html',
                             report_data=default_report_data,
                             start_date='',
                             end_date='',
                             years=list(range(datetime.now().year - 5, datetime.now().year + 1)))
        
        
@expense_incomes_bp.route('/reports/generate', methods=['POST'])
@admin_login_required
def generate_financial_report():
    """Generate and save financial report"""
    try:
        report_period = request.form.get('report_period', 'monthly')
        period_date = request.form.get('period_date', datetime.now().date().isoformat())
        notes = request.form.get('notes', '').strip()
        
        # Calculate report data
        # ... (similar calculation logic as in financial_reports function)
        
        # Save to financial_reports table
        report_data = {
            'report_period': report_period,
            'period_date': period_date,
            'total_member_income': 0,  # Calculate these
            'total_other_income': 0,
            'total_expenses': 0,
            'net_profit': 0,
            'notes': notes,
            'generated_by': session.get('admin_id'),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('financial_reports').insert(report_data).execute()
        
        flash('Financial report generated and saved successfully', 'success')
        return redirect(url_for('expense_incomes.financial_reports'))
        
    except Exception as e:
        print(f"Error generating financial report: {e}")
        flash('Error generating financial report', 'error')
        return redirect(url_for('expense_incomes.financial_reports'))

# API Endpoints for Dashboard
@expense_incomes_bp.route('/api/dashboard-stats')
@admin_login_required
def dashboard_stats():
    """Get dashboard statistics"""
    try:
        today = datetime.now().date()
        
        # Today's totals
        today_expenses_res = supabase.table('expenses')\
            .select('amount')\
            .eq('payment_date', today.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        today_expenses = sum(Decimal(r['amount']) for r in today_expenses_res.data) if today_expenses_res.data else Decimal('0')
        
        today_incomes_res = supabase.table('other_incomes')\
            .select('amount')\
            .eq('payment_date', today.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        today_incomes = sum(Decimal(r['amount']) for r in today_incomes_res.data) if today_incomes_res.data else Decimal('0')
        
        # This month totals
        month_start = datetime.now().replace(day=1).date()
        month_expenses_res = supabase.table('expenses')\
            .select('amount')\
            .gte('payment_date', month_start.isoformat())\
            .lte('payment_date', today.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        month_expenses = sum(Decimal(r['amount']) for r in month_expenses_res.data) if month_expenses_res.data else Decimal('0')
        
        month_incomes_res = supabase.table('other_incomes')\
            .select('amount')\
            .gte('payment_date', month_start.isoformat())\
            .lte('payment_date', today.isoformat())\
            .eq('status', 'approved')\
            .execute()
        
        month_incomes = sum(Decimal(r['amount']) for r in month_incomes_res.data) if month_incomes_res.data else Decimal('0')
        
        return jsonify({
            'success': True,
            'today_expenses': str(today_expenses),
            'today_incomes': str(today_incomes),
            'month_expenses': str(month_expenses),
            'month_incomes': str(month_incomes),
            'month_profit': str(month_incomes - month_expenses)
        })
        
    except Exception as e:
        print(f"Error getting dashboard stats: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Utility functions
def log_financial_activity(action, description):
    """Log financial activities"""
    try:
        supabase.table('financial_activity_log').insert({
            'action': action,
            'description': description,
            'performed_by': session.get('admin_id'),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'created_at': datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"Failed to log financial activity: {e}")
        
        
        from flask import jsonify

@expense_incomes_bp.route('/api/expense/<expense_id>', methods=['GET'])
@admin_login_required
def get_expense(expense_id):
    """Get expense details by ID"""
    try:
        # Query the expense with category name
        response = supabase.table('expenses')\
            .select('*, expense_categories(name)')\
            .eq('id', expense_id)\
            .single()\
            .execute()
        
        if not response.data:
            return jsonify({
                'success': False,
                'error': 'Expense not found'
            }), 404
        
        expense = response.data
        
        # Format the response
        formatted_expense = {
            'id': expense['id'],
            'expense_number': expense['expense_number'],
            'category_id': expense['category_id'],
            'category_name': expense['expense_categories']['name'] if expense.get('expense_categories') else 'Unknown',
            'amount': float(expense['amount']),
            'description': expense['description'],
            'payment_method': expense['payment_method'],
            'reference_number': expense['reference_number'],
            'payment_date': expense['payment_date'],
            'paid_to': expense['paid_to'],
            'status': expense['status'],
            'notes': expense['notes'],
            'approved_by': expense['approved_by'],
            'created_by': expense['created_by'],
            'created_at': expense['created_at'],
            'updated_at': expense['updated_at']
        }
        
        return jsonify({
            'success': True,
            'expense': formatted_expense
        })
        
    except Exception as e:
        print(f"Error fetching expense {expense_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
