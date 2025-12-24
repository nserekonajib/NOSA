# import os
# from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
# from functools import wraps
# from supabase import create_client, Client
# from datetime import datetime, timedelta
# from decimal import Decimal
# from dotenv import load_dotenv

# load_dotenv()

# # Initialize Supabase client
# supabase: Client = create_client(
#     os.getenv('SUPABASE_URL'),
#     os.getenv('SUPABASE_KEY')
# )

# # Create Blueprint
# dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/admin')

# # Admin required decorator
# def admin_login_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if 'admin_logged_in' not in session or not session.get('admin_logged_in'):
#             flash('Please login to access this page', 'error')
#             return redirect(url_for('adminauth.admin_login'))
#         return f(*args, **kwargs)
#     return decorated_function

# # Helper functions
# def get_today_date():
#     """Get today's date in ISO format"""
#     return datetime.now().date().isoformat()

# def get_week_range():
#     """Get start and end dates for current week"""
#     today = datetime.now().date()
#     start_of_week = today - timedelta(days=today.weekday())
#     end_of_week = start_of_week + timedelta(days=6)
#     return start_of_week.isoformat(), end_of_week.isoformat()

# def get_month_range():
#     """Get start and end dates for current month"""
#     today = datetime.now().date()
#     start_of_month = today.replace(day=1)
#     if today.month == 12:
#         end_of_month = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
#     else:
#         end_of_month = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
#     return start_of_month.isoformat(), end_of_month.isoformat()

# def calculate_percentage_change(current, previous):
#     """Calculate percentage change"""
#     if previous == 0:
#         return 100 if current > 0 else 0
#     return ((current - previous) / previous) * 100

# # Routes
# @dashboard_bp.route('/')
# @dashboard_bp.route('/dashboard')
# @admin_login_required
# def admin_dashboard():
#     """Main Admin Dashboard"""
#     try:
        
#         today = get_today_date()
#         week_start, week_end = get_week_range()
#         month_start, month_end = get_month_range()
        
#         # 1. MEMBERS STATISTICS
#         # Total members count
#         total_members_res = supabase.table('members')\
#             .select('id', count='exact')\
#             .execute()
#         total_members = total_members_res.count or 0
        
#         # New members this month
#         new_members_res = supabase.table('members')\
#             .select('id', count='exact')\
#             .gte('created_at', month_start)\
#             .execute()
#         new_members_this_month = new_members_res.count or 0
        
#         # Active members (with active status)
#         active_members_res = supabase.table('members')\
#             .select('id', count='exact')\
#             .eq('account_status', 'active')\
#             .execute()
#         active_members = active_members_res.count or 0
        
#         # Pending approvals (if you have approval system)
#         pending_members_res = supabase.table('members')\
#             .select('id', count='exact')\
#             .eq('account_status', 'pending')\
#             .execute()
#         pending_members = pending_members_res.count or 0
        
#         # 2. LOANS STATISTICS
#         # Total active loans
#         active_loans_res = supabase.table('loan_applications')\
#             .select('id', count='exact')\
#             .eq('status', 'disbursed')\
#             .execute()
#         active_loans = active_loans_res.count or 0
        
#         # Total loan amount disbursed
#         total_loans_res = supabase.table('loan_applications')\
#             .select('loan_amount')\
#             .eq('status', 'disbursed')\
#             .execute()
#         total_loan_amount = sum(Decimal(r['loan_amount']) for r in total_loans_res.data) if total_loans_res.data else Decimal('0')
        
#         # Pending loan applications
#         pending_loans_res = supabase.table('loan_applications')\
#             .select('id', count='exact')\
#             .eq('status', 'pending')\
#             .execute()
#         pending_loans = pending_loans_res.count or 0
        
#         # Loan repayment rate (simplified)
#         total_repayments_res = supabase.table('loan_repayments')\
#             .select('due_amount, paid_amount')\
#             .execute()
        
#         total_due = Decimal('0')
#         total_paid = Decimal('0')
#         if total_repayments_res.data:
#             for repayment in total_repayments_res.data:
#                 total_due += Decimal(repayment.get('due_amount', '0') or '0')
#                 total_paid += Decimal(repayment.get('paid_amount', '0') or '0')
        
#         repayment_rate = (total_paid / total_due * 100) if total_due > 0 else 0
        
#         # 3. SAVINGS STATISTICS
#         # Total savings balance
#         savings_res = supabase.table('savings_accounts')\
#             .select('current_balance')\
#             .execute()
#         total_savings = sum(Decimal(r['current_balance']) for r in savings_res.data) if savings_res.data else Decimal('0')
        
#         # 4. FINANCIAL STATISTICS
#         # Today's income (from loan repayments)
#         today_income_res = supabase.table('loan_repayments')\
#             .select('paid_amount')\
#             .eq('paid_date', today)\
#             .execute()
#         today_income = sum(Decimal(r['paid_amount']) for r in today_income_res.data) if today_income_res.data else Decimal('0')
        
#         # Monthly income
#         month_income_res = supabase.table('loan_repayments')\
#             .select('paid_amount')\
#             .gte('paid_date', month_start)\
#             .lte('paid_date', month_end)\
#             .execute()
#         month_income = sum(Decimal(r['paid_amount']) for r in month_income_res.data) if month_income_res.data else Decimal('0')
        
#         # Total expenses (from expense_incomes module if exists)
#         try:
#             month_expenses_res = supabase.table('expenses')\
#                 .select('amount')\
#                 .gte('payment_date', month_start)\
#                 .lte('payment_date', month_end)\
#                 .eq('status', 'approved')\
#                 .execute()
#             month_expenses = sum(Decimal(r['amount']) for r in month_expenses_res.data) if month_expenses_res.data else Decimal('0')
#         except:
#             month_expenses = Decimal('0')
        
#         # Net profit
#         net_profit = month_income - month_expenses
        
#         # 5. RECENT ACTIVITIES
#         # Recent members
#         recent_members_res = supabase.table('members')\
#             .select('id, full_name, member_number, created_at')\
#             .order('created_at', desc=True)\
#             .limit(5)\
#             .execute()
#         recent_members = recent_members_res.data if recent_members_res.data else []
        
#         # Recent loan applications
#         recent_loans_res = supabase.table('loan_applications')\
#             .select('id, account_number, loan_amount, status, created_at, members(full_name)')\
#             .order('created_at', desc=True)\
#             .limit(5)\
#             .execute()
#         recent_loans = recent_loans_res.data if recent_loans_res.data else []
        
#         # Recent repayments
#         recent_repayments_res = supabase.table('loan_repayments')\
#             .select('id, due_amount, paid_amount, status, paid_date, members(full_name)')\
#             .order('paid_date', desc=True)\
#             .limit(5)\
#             .execute()
#         recent_repayments = recent_repayments_res.data if recent_repayments_res.data else []
        
#         # 6. PERFORMANCE METRICS
#         # Calculate month-over-month changes
#         last_month_start = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1).date().isoformat()
#         last_month_end = (datetime.now().replace(day=1) - timedelta(days=1)).date().isoformat()
        
#         # Last month income
#         last_month_income_res = supabase.table('loan_repayments')\
#             .select('paid_amount')\
#             .gte('paid_date', last_month_start)\
#             .lte('paid_date', last_month_end)\
#             .execute()
#         last_month_income = sum(Decimal(r['paid_amount']) for r in last_month_income_res.data) if last_month_income_res.data else Decimal('0')
        
#         # Income growth
#         income_growth = calculate_percentage_change(float(month_income), float(last_month_income))
        
#         # Member growth (this month vs last month)
#         last_month_members_res = supabase.table('members')\
#             .select('id', count='exact')\
#             .gte('created_at', last_month_start)\
#             .lte('created_at', last_month_end)\
#             .execute()
#         last_month_members = last_month_members_res.count or 0
        
#         member_growth = calculate_percentage_change(new_members_this_month, last_month_members)
        
#         # 7. UPCOMING DUE DATES
#         # Loans due in next 7 days
#         next_week = (datetime.now() + timedelta(days=7)).date().isoformat()
#         upcoming_due_res = supabase.table('loan_repayments')\
#             .select('id, due_date, due_amount, members(full_name, member_number)')\
#             .gte('due_date', today)\
#             .lte('due_date', next_week)\
#             .eq('status', 'pending')\
#             .order('due_date')\
#             .limit(10)\
#             .execute()
#         upcoming_due = upcoming_due_res.data if upcoming_due_res.data else []
        
#         # 8. QUICK STATS SUMMARY
#         quick_stats = {
#             'total_members': total_members,
#             'active_loans': active_loans,
#             'total_savings': total_savings,
#             'today_income': today_income,
#             'month_income': month_income,
#             'month_expenses': month_expenses,
#             'net_profit': net_profit,
#             'repayment_rate': repayment_rate,
#             'pending_loans': pending_loans,
#             'income_growth': income_growth,
#             'member_growth': member_growth
#         }
        
#         return render_template('admin/dashboard.html',
#                              quick_stats=quick_stats,
#                              recent_members=recent_members,
#                              recent_loans=recent_loans,
#                              recent_repayments=recent_repayments,
#                              upcoming_due=upcoming_due,
#                              active_members=active_members,
#                              total_loan_amount=total_loan_amount)
        
#     except Exception as e:
#         print(f"Error loading dashboard: {e}")
#         import traceback
#         traceback.print_exc()
        
#         # Return empty dashboard on error
#         return render_template('admin/dashboard.html',
#                              quick_stats={
#                                  'total_members': 0,
#                                  'active_loans': 0,
#                                  'total_savings': 0,
#                                  'today_income': 0,
#                                  'month_income': 0,
#                                  'month_expenses': 0,
#                                  'net_profit': 0,
#                                  'repayment_rate': 0,
#                                  'pending_loans': 0,
#                                  'income_growth': 0,
#                                  'member_growth': 0
#                              },
#                              recent_members=[],
#                              recent_loans=[],
#                              recent_repayments=[],
#                              upcoming_due=[],
#                              active_members=0,
#                              total_loan_amount=0)

# @dashboard_bp.route('/api/dashboard-data')
# @admin_login_required
# def dashboard_data():
#     """API endpoint for dashboard data (for charts)"""
#     try:
#         # Get time range from request
#         period = request.args.get('period', 'monthly')  # daily, weekly, monthly, yearly
        
#         # Calculate date ranges
#         end_date = datetime.now().date()
#         if period == 'daily':
#             start_date = end_date
#             date_format = '%Y-%m-%d'
#         elif period == 'weekly':
#             start_date = end_date - timedelta(days=7)
#             date_format = '%Y-%m-%d'
#         elif period == 'monthly':
#             start_date = end_date.replace(day=1)
#             date_format = '%Y-%m'
#         elif period == 'yearly':
#             start_date = end_date.replace(month=1, day=1)
#             date_format = '%Y'
#         else:
#             start_date = end_date.replace(day=1)
#             date_format = '%Y-%m-%d'
        
#         # 1. Income over time (loan repayments)
#         income_res = supabase.table('loan_repayments')\
#             .select('paid_amount, paid_date')\
#             .gte('paid_date', start_date.isoformat())\
#             .lte('paid_date', end_date.isoformat())\
#             .not_.is_('paid_amount', 'null')\
#             .execute()
        
#         income_data = {}
#         if income_res.data:
#             for payment in income_res.data:
#                 if payment['paid_date']:
#                     date_key = datetime.fromisoformat(payment['paid_date']).strftime(date_format)
#                     amount = Decimal(payment.get('paid_amount', '0') or '0')
#                     income_data[date_key] = income_data.get(date_key, Decimal('0')) + amount
        
#         # 2. New members over time
#         members_res = supabase.table('members')\
#             .select('created_at')\
#             .gte('created_at', start_date.isoformat() + 'T00:00:00')\
#             .lte('created_at', end_date.isoformat() + 'T23:59:59')\
#             .execute()
        
#         members_data = {}
#         if members_res.data:
#             for member in members_res.data:
#                 if member['created_at']:
#                     date_key = datetime.fromisoformat(member['created_at']).strftime(date_format)
#                     members_data[date_key] = members_data.get(date_key, 0) + 1
        
#         # 3. Loan applications over time
#         loans_res = supabase.table('loan_applications')\
#             .select('created_at, status')\
#             .gte('created_at', start_date.isoformat() + 'T00:00:00')\
#             .lte('created_at', end_date.isoformat() + 'T23:59:59')\
#             .execute()
        
#         loans_data = {'pending': {}, 'approved': {}, 'rejected': {}, 'disbursed': {}}
#         if loans_res.data:
#             for loan in loans_res.data:
#                 if loan['created_at']:
#                     date_key = datetime.fromisoformat(loan['created_at']).strftime(date_format)
#                     status = loan.get('status', 'pending')
#                     if status in loans_data:
#                         loans_data[status][date_key] = loans_data[status].get(date_key, 0) + 1
        
#         # Prepare response
#         dates = sorted(set(list(income_data.keys()) + 
#                           list(members_data.keys()) + 
#                           list(loans_data['pending'].keys()) +
#                           list(loans_data['approved'].keys()) +
#                           list(loans_data['disbursed'].keys())))
        
#         chart_data = {
#             'dates': dates,
#             'income': [float(income_data.get(date, Decimal('0'))) for date in dates],
#             'new_members': [members_data.get(date, 0) for date in dates],
#             'pending_loans': [loans_data['pending'].get(date, 0) for date in dates],
#             'approved_loans': [loans_data['approved'].get(date, 0) for date in dates],
#             'disbursed_loans': [loans_data['disbursed'].get(date, 0) for date in dates]
#         }
        
#         return jsonify({
#             'success': True,
#             'period': period,
#             'chart_data': chart_data
#         })
        
#     except Exception as e:
#         print(f"Error fetching dashboard data: {e}")
#         return jsonify({'success': False, 'message': str(e)}), 500

# @dashboard_bp.route('/api/quick-stats')
# @admin_login_required
# def quick_stats():
#     """API endpoint for quick stats (for real-time updates)"""
#     try:
#         today = get_today_date()
        
#         # Today's income
#         today_income_res = supabase.table('loan_repayments')\
#             .select('paid_amount')\
#             .eq('paid_date', today)\
#             .execute()
#         today_income = sum(Decimal(r['paid_amount']) for r in today_income_res.data) if today_income_res.data else Decimal('0')
        
#         # New members today
#         new_members_today_res = supabase.table('members')\
#             .select('id', count='exact')\
#             .gte('created_at', today + 'T00:00:00')\
#             .lte('created_at', today + 'T23:59:59')\
#             .execute()
#         new_members_today = new_members_today_res.count or 0
        
#         # New loan applications today
#         new_loans_today_res = supabase.table('loan_applications')\
#             .select('id', count='exact')\
#             .gte('created_at', today + 'T00:00:00')\
#             .lte('created_at', today + 'T23:59:59')\
#             .execute()
#         new_loans_today = new_loans_today_res.count or 0
        
#         # Pending approvals
#         pending_loans_res = supabase.table('loan_applications')\
#             .select('id', count='exact')\
#             .eq('status', 'pending')\
#             .execute()
#         pending_loans = pending_loans_res.count or 0
        
#         return jsonify({
#             'success': True,
#             'today_income': str(today_income),
#             'new_members_today': new_members_today,
#             'new_loans_today': new_loans_today,
#             'pending_loans': pending_loans,
#             'timestamp': datetime.now().isoformat()
#         })
        
#     except Exception as e:
#         print(f"Error fetching quick stats: {e}")
#         return jsonify({'success': False, 'message': str(e)}), 500

# @dashboard_bp.route('/api/performance-metrics')
# @admin_login_required
# def performance_metrics():
#     """API endpoint for performance metrics"""
#     try:
#         today = datetime.now().date()
        
#         # Last month date ranges
#         if today.month == 1:
#             last_month_start = datetime(today.year - 1, 12, 1).date()
#             last_month_end = datetime(today.year - 1, 12, 31).date()
#         else:
#             last_month_start = datetime(today.year, today.month - 1, 1).date()
#             last_month_end = datetime(today.year, today.month, 1).date() - timedelta(days=1)
        
#         current_month_start = datetime(today.year, today.month, 1).date()
        
#         # Current month metrics
#         current_month_members_res = supabase.table('members')\
#             .select('id', count='exact')\
#             .gte('created_at', current_month_start.isoformat() + 'T00:00:00')\
#             .execute()
#         current_month_members = current_month_members_res.count or 0
        
#         current_month_income_res = supabase.table('loan_repayments')\
#             .select('paid_amount')\
#             .gte('paid_date', current_month_start.isoformat())\
#             .lte('paid_date', today.isoformat())\
#             .execute()
#         current_month_income = sum(Decimal(r['paid_amount']) for r in current_month_income_res.data) if current_month_income_res.data else Decimal('0')
        
#         # Last month metrics
#         last_month_members_res = supabase.table('members')\
#             .select('id', count='exact')\
#             .gte('created_at', last_month_start.isoformat() + 'T00:00:00')\
#             .lte('created_at', last_month_end.isoformat() + 'T23:59:59')\
#             .execute()
#         last_month_members = last_month_members_res.count or 0
        
#         last_month_income_res = supabase.table('loan_repayments')\
#             .select('paid_amount')\
#             .gte('paid_date', last_month_start.isoformat())\
#             .lte('paid_date', last_month_end.isoformat())\
#             .execute()
#         last_month_income = sum(Decimal(r['paid_amount']) for r in last_month_income_res.data) if last_month_income_res.data else Decimal('0')
        
#         # Calculate growth percentages
#         member_growth = calculate_percentage_change(current_month_members, last_month_members)
#         income_growth = calculate_percentage_change(float(current_month_income), float(last_month_income))
        
#         # Loan approval rate
#         total_loans_res = supabase.table('loan_applications')\
#             .select('status', count='exact')\
#             .execute()
        
#         approved_loans = 0
#         total_processed = 0
#         if hasattr(total_loans_res, 'data'):
#             for loan in total_loans_res.data:
#                 total_processed += 1
#                 if loan['status'] in ['approved', 'disbursed']:
#                     approved_loans += 1
        
#         approval_rate = (approved_loans / total_processed * 100) if total_processed > 0 else 0
        
#         # Average loan size
#         disbursed_loans_res = supabase.table('loan_applications')\
#             .select('loan_amount')\
#             .eq('status', 'disbursed')\
#             .execute()
        
#         if disbursed_loans_res.data:
#             total_disbursed = sum(Decimal(r['loan_amount']) for r in disbursed_loans_res.data)
#             average_loan_size = total_disbursed / len(disbursed_loans_res.data)
#         else:
#             average_loan_size = Decimal('0')
        
#         return jsonify({
#             'success': True,
#             'member_growth': member_growth,
#             'income_growth': income_growth,
#             'approval_rate': approval_rate,
#             'average_loan_size': str(average_loan_size),
#             'current_month_members': current_month_members,
#             'current_month_income': str(current_month_income)
#         })
        
#     except Exception as e:
#         print(f"Error fetching performance metrics: {e}")
#         return jsonify({'success': False, 'message': str(e)}), 500

