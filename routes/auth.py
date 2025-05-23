from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import User, Admin, RegularUser, db
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if isinstance(current_user, Admin):
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('user.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user_type = request.form.get('user_type')
        
        if user_type == 'admin':
            user = Admin.query.filter_by(email=email).first()
        else:
            user = RegularUser.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if isinstance(user, RegularUser) and user.is_blocked:
                flash('Your account has been blocked. Please contact the administrator.', 'danger')
                return redirect(url_for('auth.login'))
            
            login_user(user)
            flash('Logged in successfully!', 'success')
            
            if isinstance(user, Admin):
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('user.dashboard'))
        
        flash('Invalid email or password.', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('user.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        
        # Check if email already exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('auth.register'))
        
        # Create new user
        user = RegularUser(
            email=email,
            name=name,
            phone=phone,
            address=address
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('auth.login'))

# Create admin user if not exists
def create_admin():
    # First admin
    admin1 = Admin.query.filter_by(email='admin@parking.com').first()
    if not admin1:
        admin1 = Admin(
            email='admin@parking.com',
            name='Admin'
        )
        admin1.set_password('admin123')  # Default password
        db.session.add(admin1)
    
    # Second admin
    admin2 = Admin.query.filter_by(email='superadmin@parking.com').first()
    if not admin2:
        admin2 = Admin(
            email='superadmin@parking.com',
            name='Super Admin'
        )
        admin2.set_password('super123')  # Default password
        db.session.add(admin2)
    
    db.session.commit()
