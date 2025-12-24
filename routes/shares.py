import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from supabase import create_client, Client
from datetime import datetime, date
from decimal import Decimal
import uuid
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Create Blueprint
shares_admin_bp = Blueprint('shares_admin', __name__, url_prefix='/admin/shares')

# Admin required decorator
def admin_login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session.get('admin_logged_in'):
            flash('Please login to access this page', 'error')
            return redirect(url_for('adminauth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function
def get_default_shares_context():
    """Get default context for shares templates when errors occur"""
    return {
        'current_share_value': None,
        'total_shares': 0,
        'total_members': 0,
        'members_with_shares': 0,
        'total_share_value': Decimal('0'),
        'transactions': [],
        'top_shareholders': [],
        'value_history': [],
        'monthly_stats': {}
    }
    
    
@shares_admin_bp.route('/')
@admin_login_required
def manage_shares():
    """Admin shares management dashboard"""
    try:
        # Get current share value
        share_value_res = supabase.table('share_value')\
            .select('*')\
            .order('effective_date', desc=True)\
            .limit(1)\
            .execute()
        
        current_share_value = share_value_res.data[0] if share_value_res.data else None
        
        # Get total shares statistics
        stats_res = supabase.table('members')\
            .select('shares_owned')\
            .execute()
        
        members = stats_res.data if stats_res.data else []
        total_shares = sum(m.get('shares_owned', 0) for m in members)
        total_members = len(members)
        members_with_shares = sum(1 for m in members if m.get('shares_owned', 0) > 0)
        
        # Calculate total share value
        if current_share_value:
            total_share_value = total_shares * Decimal(str(current_share_value['value_per_share']))
        else:
            total_share_value = Decimal('0')
        
        # Get recent share transactions
        transactions_res = supabase.table('share_transactions')\
            .select('*, members(full_name, member_number)')\
            .order('transaction_date', desc=True)\
            .limit(20)\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        
        # Get top shareholders
        top_shareholders_res = supabase.table('members')\
            .select('id, full_name, member_number, shares_owned')\
            .order('shares_owned', desc=True)\
            .limit(10)\
            .execute()
        
        top_shareholders = top_shareholders_res.data if top_shareholders_res.data else []
        
        # Get share value history
        value_history_res = supabase.table('share_value')\
            .select('*')\
            .order('effective_date', desc=True)\
            .execute()
        
        value_history = value_history_res.data if value_history_res.data else []
        
        # Get monthly share purchase statistics
        monthly_stats = get_monthly_share_statistics()
        
        today_date = date.today().isoformat()  # Add this line
        
        return render_template('admin/shares/manage_shares.html',
                             current_share_value=current_share_value,
                             total_shares=total_shares,
                             total_members=total_members,
                             members_with_shares=members_with_shares,
                             total_share_value=total_share_value,
                             transactions=transactions,
                             top_shareholders=top_shareholders,
                             value_history=value_history,
                             monthly_stats=monthly_stats,
                             today_date=today_date)  # Add this line
        
    except Exception as e:
        print(f"Error loading shares dashboard: {e}")
        flash('Error loading shares information', 'error')
        
        today_date = date.today().isoformat()  # Add this line
        
        return render_template('admin/shares/manage_shares.html',
                             current_share_value=None,
                             total_shares=0,
                             total_members=0,
                             members_with_shares=0,
                             total_share_value=Decimal('0'),
                             transactions=[],
                             top_shareholders=[],
                             value_history=[],
                             monthly_stats={},
                             today_date=today_date)  # Add this line
        

@shares_admin_bp.route('/update-share-value', methods=['POST'])
@admin_login_required
def update_share_value():
    """Update the current share value"""
    try:
        admin_id = session.get('admin_id')
        value_per_share = Decimal(request.form.get('value_per_share', '0'))
        effective_date = request.form.get('effective_date', date.today().isoformat())
        description = request.form.get('description', '').strip()
        
        if value_per_share <= 0:
            flash('Please enter a valid share value', 'error')
            return redirect(url_for('shares_admin.manage_shares'))
        
        # Create new share value record
        share_value_data = {
            'value_per_share': str(value_per_share),
            'effective_date': effective_date,
            'description': description,
            'updated_by': admin_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('share_value').insert(share_value_data).execute()
        
        # Log activity
        log_admin_activity(admin_id, 'share_value_update', 
                          f'Updated share value to UGX {value_per_share:,.0f} per share')
        
        flash(f'Share value updated to UGX {value_per_share:,.0f} per share', 'success')
        return redirect(url_for('shares_admin.manage_shares'))
        
    except Exception as e:
        print(f"Error updating share value: {e}")
        flash('Error updating share value', 'error')
        return redirect(url_for('shares_admin.manage_shares'))

@shares_admin_bp.route('/members')
@admin_login_required
def members_shares():
    """View all members and their shares"""
    try:
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = 20
        
        # Build query
        query = supabase.table('members')\
            .select('id, member_number, full_name, email, phone_number, shares_owned, account_status, created_at')\
            .order('shares_owned', desc=True)
        
        if search:
            query = query.or_(f"full_name.ilike.%{search}%,member_number.ilike.%{search}%,email.ilike.%{search}%")
        
        # Get paginated results
        from_index = (page - 1) * per_page
        to_index = from_index + per_page - 1
        
        members_res = query.range(from_index, to_index).execute()
        members = members_res.data if members_res.data else []
        
        # Get total count for pagination
        count_res = supabase.table('members')\
            .select('id', count='exact')\
            .execute()
        
        total_members = count_res.count if hasattr(count_res, 'count') else 0
        total_pages = (total_members + per_page - 1) // per_page
        
        # Get current share value
        share_value_res = supabase.table('share_value')\
            .select('value_per_share')\
            .order('effective_date', desc=True)\
            .limit(1)\
            .execute()
        
        current_share_value = Decimal(share_value_res.data[0]['value_per_share']) if share_value_res.data else Decimal('1000')
        
        return render_template('admin/shares/members_shares.html',
                             members=members,
                             search=search,
                             page=page,
                             per_page=per_page,
                             total_pages=total_pages,
                             total_members=total_members,
                             current_share_value=current_share_value)
        
    except Exception as e:
        print(f"Error loading members shares: {e}")
        flash('Error loading members shares', 'error')
        return render_template('admin/shares/members_shares.html')

@shares_admin_bp.route('/member/<member_id>/shares')
@admin_login_required
def member_shares_detail(member_id):
    """View detailed share information for a specific member"""
    try:
        # Get member details
        member_res = supabase.table('members')\
            .select('*')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data if member_res.data else None
        
        if not member:
            flash('Member not found', 'error')
            return redirect(url_for('shares_admin.members_shares'))
        
        # Get current share value
        share_value_res = supabase.table('share_value')\
            .select('*')\
            .order('effective_date', desc=True)\
            .limit(1)\
            .execute()
        
        current_share_value = share_value_res.data[0] if share_value_res.data else {'value_per_share': 1000, 'currency': 'UGX'}
        
        # Calculate member's share value
        shares_owned = member.get('shares_owned', 0)
        total_value = shares_owned * Decimal(current_share_value['value_per_share'])
        
        # Get share transactions
        transactions_res = supabase.table('share_transactions')\
            .select('*')\
            .eq('member_id', member_id)\
            .order('transaction_date', desc=True)\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        
        # Get share purchase summary
        purchase_summary = {
            'total_shares': shares_owned,
            'total_investment': sum(Decimal(t.get('total_amount', '0')) for t in transactions),
            'total_transactions': len(transactions),
            'first_purchase': transactions[-1]['transaction_date'][:10] if transactions else 'N/A',
            'last_purchase': transactions[0]['transaction_date'][:10] if transactions else 'N/A'
        }
        
        return render_template('admin/shares/member_shares_detail.html',
                             member=member,
                             current_share_value=current_share_value,
                             total_value=total_value,
                             transactions=transactions,
                             purchase_summary=purchase_summary)
        
    except Exception as e:
        print(f"Error loading member shares detail: {e}")
        flash('Error loading member share details', 'error')
        return redirect(url_for('shares_admin.members_shares'))

@shares_admin_bp.route('/manual-share-purchase', methods=['POST'])
@admin_login_required
def manual_share_purchase():
    """Manually record share purchase for a member (e.g., cash payment)"""
    try:
        admin_id = session.get('admin_id')
        member_id = request.form.get('member_id')
        shares = int(request.form.get('shares', '0'))
        payment_method = request.form.get('payment_method', 'cash')
        reference = request.form.get('reference', '')
        notes = request.form.get('notes', '').strip()
        
        if not member_id or shares <= 0:
            flash('Please enter valid member and number of shares', 'error')
            return redirect(url_for('shares_admin.members_shares'))
        
        # Get current share value
        share_value_res = supabase.table('share_value')\
            .select('*')\
            .order('effective_date', desc=True)\
            .limit(1)\
            .execute()
        
        if not share_value_res.data:
            flash('Share price not configured', 'error')
            return redirect(url_for('shares_admin.members_shares'))
        
        share_value = share_value_res.data[0]
        price_per_share = Decimal(share_value['value_per_share'])
        total_amount = price_per_share * shares
        
        # Get member details
        member_res = supabase.table('members')\
            .select('shares_owned, full_name, member_number')\
            .eq('id', member_id)\
            .single()\
            .execute()
        
        member = member_res.data
        current_shares = member.get('shares_owned', 0)
        new_shares = current_shares + shares
        
        # Create share transaction record
        transaction_data = {
            'member_id': member_id,
            'shares': shares,
            'price_per_share': str(price_per_share),
            'currency': share_value['currency'],
            'transaction_type': 'purchase',
            'reference': reference or f'MANUAL-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            'notes': f'Manual purchase by admin: {notes}',
            'payment_method': payment_method,
            'transaction_date': datetime.now().isoformat(),
            'processed_by': admin_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        supabase.table('share_transactions').insert(transaction_data).execute()
        
        # Update member's shares
        supabase.table('members')\
            .update({
                'shares_owned': new_shares,
                'updated_at': datetime.now().isoformat()
            })\
            .eq('id', member_id)\
            .execute()
        
        # Log activity
        log_admin_activity(admin_id, 'manual_share_purchase',
                          f'Manually purchased {shares} shares for {member["full_name"]} ({member["member_number"]})')
        
        flash(f'Successfully recorded purchase of {shares} shares for {member["full_name"]}', 'success')
        return redirect(url_for('shares_admin.member_shares_detail', member_id=member_id))
        
    except Exception as e:
        print(f"Error in manual share purchase: {e}")
        flash('Error recording share purchase', 'error')
        return redirect(url_for('shares_admin.members_shares'))
    


@shares_admin_bp.route('/transactions')
@admin_login_required
def share_transactions():
    """View all share transactions with filtering"""
    try:
        # Get filter parameters
        transaction_type = request.args.get('type', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        member_search = request.args.get('member_search', '')
        page = int(request.args.get('page', 1))
        per_page = 50
        
        # Build query
        query = supabase.table('share_transactions')\
            .select('*, members(full_name, member_number)')\
            .order('transaction_date', desc=True)
        
        if transaction_type:
            query = query.eq('transaction_type', transaction_type)
        
        if start_date:
            query = query.gte('transaction_date', f'{start_date}T00:00:00')
        
        if end_date:
            query = query.lte('transaction_date', f'{end_date}T23:59:59')
        
        if member_search:
            # First get member IDs
            members_res = supabase.table('members')\
                .select('id')\
                .or_(f"full_name.ilike.%{member_search}%,member_number.ilike.%{member_search}%")\
                .execute()
            
            if members_res.data:
                member_ids = [m['id'] for m in members_res.data]
                query = query.in_('member_id', member_ids)
        
        # Get paginated results
        from_index = (page - 1) * per_page
        to_index = from_index + per_page - 1
        
        transactions_res = query.range(from_index, to_index).execute()
        transactions = transactions_res.data if transactions_res.data else []
        
        # Get total count for pagination
        count_query = supabase.table('share_transactions').select('id', count='exact')
        
        if transaction_type:
            count_query = count_query.eq('transaction_type', transaction_type)
        
        count_res = count_query.execute()
        total_transactions = count_res.count if hasattr(count_res, 'count') else 0
        total_pages = (total_transactions + per_page - 1) // per_page
        
        # Calculate totals
        totals = {
            'total_shares': sum(t.get('shares', 0) for t in transactions if t.get('transaction_type') == 'purchase'),
            'total_amount': sum(Decimal(t.get('total_amount', '0')) for t in transactions),
            'total_transactions': len(transactions)
        }
        
        return render_template('admin/shares/transactions.html',
                             transactions=transactions,
                             transaction_type=transaction_type,
                             start_date=start_date,
                             end_date=end_date,
                             member_search=member_search,
                             page=page,
                             per_page=per_page,
                             total_pages=total_pages,
                             totals=totals)
        
    except Exception as e:
        print(f"Error loading share transactions: {e}")
        flash('Error loading share transactions', 'error')
        return render_template('admin/shares/transactions.html')

@shares_admin_bp.route('/reports')
@admin_login_required
def share_reports():
    """Generate share reports"""
    try:
        report_type = request.args.get('type', 'monthly')
        
        if report_type == 'monthly':
            # Monthly share purchase report
            monthly_stats = get_monthly_share_statistics(detailed=True)
            return render_template('admin/shares/reports/monthly.html',
                                 monthly_stats=monthly_stats,
                                 report_type=report_type)
        
        elif report_type == 'member_summary':
            # Member share summary report
            members_res = supabase.table('members')\
                .select('id, member_number, full_name, shares_owned')\
                .order('shares_owned', desc=True)\
                .execute()
            
            members = members_res.data if members_res.data else []
            
            # Get current share value
            share_value_res = supabase.table('share_value')\
                .select('value_per_share')\
                .order('effective_date', desc=True)\
                .limit(1)\
                .execute()
            
            current_share_value = Decimal(share_value_res.data[0]['value_per_share']) if share_value_res.data else Decimal('1000')
            
            return render_template('admin/shares/reports/member_summary.html',
                                 members=members,
                                 current_share_value=current_share_value,
                                 report_type=report_type)
        
        elif report_type == 'transaction_summary':
            # Transaction summary report
            start_date = request.args.get('start_date', (date.today().replace(day=1)).isoformat())
            end_date = request.args.get('end_date', date.today().isoformat())
            
            transactions_res = supabase.table('share_transactions')\
                .select('*, members(full_name, member_number)')\
                .gte('transaction_date', f'{start_date}T00:00:00')\
                .lte('transaction_date', f'{end_date}T23:59:59')\
                .order('transaction_date', desc=True)\
                .execute()
            
            transactions = transactions_res.data if transactions_res.data else []
            
            # Calculate summary
            summary = {
                'total_shares': sum(t.get('shares', 0) for t in transactions),
                'total_amount': sum(Decimal(t.get('total_amount', '0')) for t in transactions),
                'purchase_count': sum(1 for t in transactions if t.get('transaction_type') == 'purchase'),
                'sale_count': sum(1 for t in transactions if t.get('transaction_type') == 'sale'),
                'total_transactions': len(transactions)
            }
            
            return render_template('admin/shares/reports/transaction_summary.html',
                                 transactions=transactions,
                                 start_date=start_date,
                                 end_date=end_date,
                                 summary=summary,
                                 report_type=report_type)
        
        else:
            flash('Invalid report type', 'error')
            return redirect(url_for('shares_admin.share_reports'))
        
    except Exception as e:
        print(f"Error generating share reports: {e}")
        flash('Error generating reports', 'error')
        return redirect(url_for('shares_admin.manage_shares'))

@shares_admin_bp.route('/export-report')
@admin_login_required
def export_report():
    """Export share report as CSV"""
    try:
        report_type = request.args.get('type', 'monthly')
        
        if report_type == 'monthly':
            monthly_stats = get_monthly_share_statistics(detailed=True)
            
            # Create CSV
            import csv
            from io import StringIO
            from flask import make_response
            
            si = StringIO()
            cw = csv.writer(si)
            
            # Write header
            cw.writerow(['Month', 'Total Shares', 'Total Amount (UGX)', 'Number of Transactions', 'Average Share Price'])
            
            # Write data
            for month, stats in monthly_stats.items():
                cw.writerow([
                    month,
                    stats.get('total_shares', 0),
                    stats.get('total_amount', 0),
                    stats.get('transaction_count', 0),
                    stats.get('average_price', 0)
                ])
            
            output = make_response(si.getvalue())
            output.headers["Content-Disposition"] = "attachment; filename=monthly_share_report.csv"
            output.headers["Content-type"] = "text/csv"
            return output
        
        else:
            flash('Export not available for this report type', 'error')
            return redirect(url_for('shares_admin.share_reports'))
        
    except Exception as e:
        print(f"Error exporting report: {e}")
        flash('Error exporting report', 'error')
        return redirect(url_for('shares_admin.share_reports'))

def get_monthly_share_statistics(detailed=False):
    """Get monthly share purchase statistics"""
    try:
        # Get transactions for the last 12 months
        one_year_ago = datetime.now().replace(year=datetime.now().year - 1).isoformat()
        
        transactions_res = supabase.table('share_transactions')\
            .select('*')\
            .gte('transaction_date', one_year_ago)\
            .eq('transaction_type', 'purchase')\
            .execute()
        
        transactions = transactions_res.data if transactions_res.data else []
        
        # Group by month
        monthly_stats = {}
        
        for transaction in transactions:
            trans_date = datetime.fromisoformat(transaction['transaction_date'].replace('Z', '+00:00'))
            month_key = trans_date.strftime('%Y-%m')
            
            if month_key not in monthly_stats:
                monthly_stats[month_key] = {
                    'total_shares': 0,
                    'total_amount': Decimal('0'),
                    'transaction_count': 0,
                    'transactions': [] if detailed else None
                }
            
            monthly_stats[month_key]['total_shares'] += transaction.get('shares', 0)
            monthly_stats[month_key]['total_amount'] += Decimal(str(transaction.get('total_amount', '0')))
            monthly_stats[month_key]['transaction_count'] += 1
            
            if detailed and 'transactions' in monthly_stats[month_key]:
                monthly_stats[month_key]['transactions'].append(transaction)
        
        # Calculate average price for each month
        for month, stats in monthly_stats.items():
            if stats['total_shares'] > 0:
                stats['average_price'] = stats['total_amount'] / stats['total_shares']
            else:
                stats['average_price'] = Decimal('0')
        
        # Sort by month descending
        sorted_stats = dict(sorted(monthly_stats.items(), reverse=True))
        
        return sorted_stats
        
    except Exception as e:
        print(f"Error getting monthly statistics: {e}")
        return {}

def log_admin_activity(admin_id, action, description):
    """Log admin activity"""
    try:
        activity_data = {
            'admin_id': admin_id,
            'action': action,
            'description': description,
            'ip_address': request.remote_addr,
            'user_agent': request.user_agent.string,
            'created_at': datetime.now().isoformat()
        }
        
        supabase.table('admin_activity_logs').insert(activity_data).execute()
    except Exception as e:
        print(f"Error logging admin activity: {e}")
        
        
@shares_admin_bp.route('/api/transaction/<transaction_id>')
@admin_login_required
def get_transaction_details(transaction_id):
    """Get detailed transaction information for modal view"""
    try:
        transaction_res = supabase.table('share_transactions')\
            .select('*, members(full_name, member_number)')\
            .eq('id', transaction_id)\
            .single()\
            .execute()
        
        transaction = transaction_res.data if transaction_res.data else None
        
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404
        
        # Format the data
        transaction_details = {
            'id': transaction.get('id'),
            'member_id': transaction.get('member_id'),
            'member_name': transaction.get('members', {}).get('full_name') if transaction.get('members') else None,
            'member_number': transaction.get('members', {}).get('member_number') if transaction.get('members') else None,
            'shares': transaction.get('shares', 0),
            'price_per_share': str(transaction.get('price_per_share', '0')),
            'total_amount': str(transaction.get('total_amount', '0')),
            'transaction_type': transaction.get('transaction_type'),
            'payment_method': transaction.get('payment_method'),
            'reference': transaction.get('reference'),
            'notes': transaction.get('notes'),
            'transaction_date': transaction.get('transaction_date'),
            'created_at': transaction.get('created_at')
        }
        
        return jsonify(transaction_details)
        
    except Exception as e:
        print(f"Error getting transaction details: {e}")
        return jsonify({'error': 'Failed to load transaction details'}), 500
    

# Register the blueprint in your main app
# app.register_blueprint(shares_admin_bp)