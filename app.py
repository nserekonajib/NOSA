from flask import Flask, render_template, session, redirect, url_for
from routes.adminauth import adminauth_bp
from datetime import datetime
import os
from dotenv import load_dotenv
from routes.members import members_bp
from routes.saving import savings_bp
from routes.loans import loans_bp
from routes.transactions import expense_incomes_bp
from routes.member import member_bp
from routes.memberauth import memberauth_bp
from flask_wtf.csrf import CSRFProtect
from routes.shares import shares_admin_bp



load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-change-this-in-production')

# Register blueprints
app.register_blueprint(adminauth_bp)
app.register_blueprint(members_bp)
app.register_blueprint(savings_bp)
app.register_blueprint(loans_bp)
app.register_blueprint(expense_incomes_bp)
app.register_blueprint(member_bp)
app.register_blueprint(memberauth_bp)
app.register_blueprint(shares_admin_bp)


# Context processor for template variables
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# In your main app or in an initialization function

@app.template_filter('format_date')
def format_date(value, format='%b %d, %Y'):
    if value is None:
        return "N/A"
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.strftime(format)


# Admin dashboard route (protected)
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_logged_in' not in session or not session.get('admin_logged_in'):
        return redirect(url_for('adminauth.admin_login'))
    
    # Check OTP if required
    if session.get('otp_required') and not session.get('otp_verified', False):
        return redirect(url_for('adminauth.verify_otp'))
    
    return redirect(url_for('members.members_list'))


# Home route
@app.route('/')
def home():
    return redirect(url_for('memberauth.member_login'))

from waitress import serve

if __name__ == '__main__':
    # Remove app.run(), replace with waitress

    port = int(os.environ.get("PORT", 5555))
    serve(app, host="0.0.0.0", port=port)

