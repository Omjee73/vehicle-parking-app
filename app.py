from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager
from extensions import db
from routes.auth import auth_bp, create_admin
from routes.admin import admin_bp
from routes.user import user_bp
from models import User, Admin, RegularUser, ParkingLot, ParkingSpot, Reservation

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this in production
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parking.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    
    # Initialize login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        create_admin()  # Create admin user if not exists
    
    # Root route
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
