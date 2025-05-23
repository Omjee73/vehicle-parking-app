from datetime import datetime
from flask_login import UserMixin
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash

# Base User model for authentication
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    user_type = db.Column(db.String(10), nullable=False)  # 'admin' or 'user'
    
    __mapper_args__ = {
        'polymorphic_identity': 'user',
        'polymorphic_on': user_type
    }
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Admin model
class Admin(User):
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    total_revenue = db.Column(db.Float, default=0.0)
    
    __mapper_args__ = {
        'polymorphic_identity': 'admin',
    }

# Regular User model
class RegularUser(User):
    __tablename__ = 'regular_users'
    
    id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    is_blocked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __mapper_args__ = {
        'polymorphic_identity': 'regular_user',
    }

# Parking Lot model
class ParkingLot(db.Model):
    __tablename__ = 'parking_lots'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    prime_location_name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    pin_code = db.Column(db.String(10), nullable=False)
    price_per_hour = db.Column(db.Float, nullable=False)
    maximum_spots = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    spots = db.relationship('ParkingSpot', backref='lot', lazy=True, cascade="all, delete-orphan")

# Parking Spot model
class ParkingSpot(db.Model):
    __tablename__ = 'parking_spots'
    
    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lots.id'), nullable=False)
    spot_number = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(1), default='A')  # A: Available, O: Occupied

    def __repr__(self):
        return f'<ParkingSpot {self.spot_number}>'

# Time Slot model
class TimeSlot(db.Model):
    __tablename__ = 'time_slots'
    
    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lots.id'), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    price = db.Column(db.Float, nullable=False)  # Price for 30 minutes

    def __repr__(self):
        return f'<TimeSlot {self.start_time}-{self.end_time}>'

# Reservation model
class Reservation(db.Model):
    __tablename__ = 'reservations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('regular_users.id'), nullable=False)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spots.id'), nullable=False)
    time_slot_id = db.Column(db.Integer, db.ForeignKey('time_slots.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, completed, cancelled
    total_cost = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    leaving_timestamp = db.Column(db.DateTime)
    car_name = db.Column(db.String(100))
    car_number = db.Column(db.String(20))

    # Relationships
    user = db.relationship('RegularUser', backref=db.backref('reservations', lazy=True))
    spot = db.relationship('ParkingSpot', backref=db.backref('reservations', lazy=True))
    time_slot = db.relationship('TimeSlot', backref=db.backref('reservations', lazy=True))

    def calculate_cost(self):
        if not self.leaving_timestamp:
            return self.time_slot.price
        duration = (self.leaving_timestamp - self.created_at).total_seconds() / 3600  # hours
        return duration * self.spot.lot.price_per_hour
