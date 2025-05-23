from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from models import RegularUser, ParkingLot, ParkingSpot, Reservation, db, TimeSlot, User, Admin
from datetime import datetime, timedelta
from sqlalchemy import func
import pdfkit
import io

user_bp = Blueprint('user', __name__, url_prefix='/user')

@user_bp.before_request
@login_required
def before_request():
    if not isinstance(current_user, RegularUser):
        flash('Access denied. User privileges required.', 'danger')
        if isinstance(current_user, Admin):
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('auth.login'))
    
    if current_user.is_blocked:
        flash('Your account has been blocked. Please contact the administrator.', 'danger')
        return redirect(url_for('auth.logout'))

# User Dashboard
@user_bp.route('/')
def dashboard():
    # Get user's active reservation
    active_reservation = Reservation.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).first()
    
    # Get selected location from query parameters
    selected_location = request.args.get('location', '')
    
    # Get all unique locations for the filter dropdown
    locations = db.session.query(ParkingLot.prime_location_name).distinct().all()
    locations = [loc[0] for loc in locations]
    
    # Get available parking lots with optional location filter
    query = ParkingLot.query
    if selected_location:
        query = query.filter_by(prime_location_name=selected_location)
    lots = query.all()
    
    return render_template('user/dashboard.html',
                         active_reservation=active_reservation,
                         lots=lots,
                         locations=locations,
                         selected_location=selected_location)

# Book a Parking Spot
@user_bp.route('/book', methods=['GET', 'POST'])
@login_required
def book_spot():
    if request.method == 'POST':
        lot_id = request.form.get('lot_id')
        date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        time_slot_ids = request.form.getlist('time_slot')  # Get list of selected time slots
        car_name = request.form.get('car_name')
        car_number = request.form.get('car_number')
        
        if not lot_id or not date or not time_slot_ids:
            flash('Please fill in all required fields!', 'danger')
            return redirect(url_for('user.book_spot'))
        
        try:
            total_cost = 0
            for time_slot_id in time_slot_ids:
                time_slot = TimeSlot.query.get(time_slot_id)
                if not time_slot:
                    continue
                
                # Check if user already has a booking for this date and time slot
                existing_booking = Reservation.query.filter_by(
                    user_id=current_user.id,
                    date=date,
                    time_slot_id=time_slot_id,
                    status='active'
                ).first()
                
                if existing_booking:
                    flash(f'You already have a booking for time slot {time_slot.start_time.strftime("%H:%M")} - {time_slot.end_time.strftime("%H:%M")}!', 'warning')
                    continue
                
                # Check if time slot is already booked by another user
                slot_booked = Reservation.query.filter_by(
                    date=date,
                    time_slot_id=time_slot_id,
                    status='active'
                ).first()
                
                if slot_booked:
                    flash(f'Time slot {time_slot.start_time.strftime("%H:%M")} - {time_slot.end_time.strftime("%H:%M")} is already booked by another user!', 'warning')
                    continue
                
                # Find an available spot
                spot = ParkingSpot.query.filter_by(
                    lot_id=lot_id,
                    status='A'
                ).first()
                
                if not spot:
                    flash('No spots available for the selected time slot!', 'danger')
                    return redirect(url_for('user.book_spot'))
                
                # Create reservation
                reservation = Reservation(
                    user_id=current_user.id,
                    spot_id=spot.id,
                    time_slot_id=time_slot_id,
                    date=date,
                    total_cost=time_slot.price,
                    car_name=car_name,
                    car_number=car_number
                )
                
                # Update spot status
                spot.status = 'O'
                
                total_cost += time_slot.price
                db.session.add(reservation)
            
            if total_cost > 0:
                db.session.commit()
                flash(f'Parking spot(s) booked successfully! Total cost: ₹{total_cost:.2f}', 'success')
            else:
                flash('No valid bookings were made.', 'warning')
            
            return redirect(url_for('user.history'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error booking parking spot: {str(e)}', 'danger')
            return redirect(url_for('user.book_spot'))
    
    lot_id = request.args.get('lot_id')
    if not lot_id:
        flash('Please select a parking lot first!', 'warning')
        return redirect(url_for('user.dashboard'))
    
    lot = ParkingLot.query.get_or_404(lot_id)
    
    # Get today's date
    today = datetime.now().date()
    
    # Get all time slots for the lot
    time_slots = TimeSlot.query.filter_by(lot_id=lot_id).order_by(TimeSlot.start_time).all()
    
    # Filter out time slots that are already booked for today
    available_slots = []
    for slot in time_slots:
        # Check if slot is already booked
        slot_booked = Reservation.query.filter_by(
            date=today,
            time_slot_id=slot.id,
            status='active'
        ).first()
        
        if not slot_booked:
            available_slots.append(slot)
    
    return render_template('user/book_parking.html',
                         lot=lot,
                         time_slots=available_slots,
                         now=datetime.now())

# Release Parking Spot
@user_bp.route('/release/<int:reservation_id>', methods=['POST'])
@login_required
def release_spot(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    
    if reservation.user_id != current_user.id:
        flash('You are not authorized to release this spot!', 'danger')
        return redirect(url_for('user.history'))
    
    if reservation.status != 'active':
        flash('This reservation is not active!', 'warning')
        return redirect(url_for('user.history'))
    
    try:
        # Calculate release cost (50% of the time slot price)
        time_slot = TimeSlot.query.get(reservation.time_slot_id)
        if time_slot:
            release_cost = time_slot.price * 0.5
        else:
            release_cost = 0
        
        # Update reservation
        reservation.status = 'R'
        reservation.release_time = datetime.now()
        reservation.total_cost = release_cost
        
        # Update spot status
        spot = ParkingSpot.query.get(reservation.spot_id)
        if spot:
            spot.status = 'A'
        
        db.session.commit()
        flash(f'Parking spot released successfully! Release cost: ₹{release_cost:.2f}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error releasing parking spot: {str(e)}', 'danger')
    
    return redirect(url_for('user.history'))

# Booking History
@user_bp.route('/history')
def history():
    reservations = Reservation.query.filter_by(
        user_id=current_user.id
    ).order_by(Reservation.created_at.desc()).all()
    
    return render_template('user/history.html', reservations=reservations)

# User Summary
@user_bp.route('/summary')
def summary():
    # Get total bookings
    total_bookings = Reservation.query.filter_by(user_id=current_user.id).count()
    
    # Get active bookings
    active_bookings = Reservation.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).count()
    
    # Calculate total duration and total cost
    total_duration = 0
    total_cost = 0
    
    # Get all completed and released reservations
    completed_reservations = Reservation.query.filter(
        Reservation.user_id == current_user.id,
        Reservation.status.in_(['completed', 'R'])
    ).all()
    
    for reservation in completed_reservations:
        # Add the time slot duration (30 minutes = 0.5 hours)
        total_duration += 0.5
        # Add the reservation cost
        total_cost += reservation.total_cost or 0
    
    # Get lot-wise summary
    lot_summary = db.session.query(
        ParkingLot.name,
        func.count(Reservation.id).label('total_bookings'),
        func.sum(Reservation.total_cost).label('total_cost')
    ).select_from(Reservation).join(
        ParkingSpot, Reservation.spot_id == ParkingSpot.id
    ).join(
        ParkingLot, ParkingSpot.lot_id == ParkingLot.id
    ).filter(
        Reservation.user_id == current_user.id,
        Reservation.status.in_(['completed', 'R'])
    ).group_by(ParkingLot.id, ParkingLot.name).all()
    
    # Get booking history data for the last 7 days
    booking_data = []
    booking_labels = []
    for i in range(6, -1, -1):
        date = datetime.now().date() - timedelta(days=i)
        daily_bookings = Reservation.query.filter(
            Reservation.user_id == current_user.id,
            func.date(Reservation.created_at) == date
        ).count()
        booking_data.append(daily_bookings)
        booking_labels.append(date.strftime('%Y-%m-%d'))
    
    # Get spending pattern data for the last 7 days
    spending_data = []
    spending_labels = []
    for i in range(6, -1, -1):
        date = datetime.now().date() - timedelta(days=i)
        daily_spending = db.session.query(func.sum(Reservation.total_cost))\
            .filter(
                Reservation.user_id == current_user.id,
                func.date(Reservation.created_at) == date,
                Reservation.status.in_(['completed', 'R'])
            ).scalar() or 0
        spending_data.append(float(daily_spending))
        spending_labels.append(date.strftime('%Y-%m-%d'))
    
    return render_template('user/summary.html',
                         total_bookings=total_bookings,
                         active_bookings=active_bookings,
                         total_duration=round(total_duration, 1),
                         total_cost=round(total_cost, 2),
                         lot_summary=lot_summary,
                         booking_data=booking_data,
                         booking_labels=booking_labels,
                         spending_data=spending_data,
                         spending_labels=spending_labels)

@user_bp.route('/receipt/<int:reservation_id>')
@login_required
def view_receipt(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.history'))
    return render_template('user/receipt.html', reservation=reservation, user=current_user)

@user_bp.route('/download_receipt/<int:reservation_id>')
@login_required
def download_receipt(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.user_id != current_user.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user.history'))
    
    # Generate PDF
    html = render_template('user/receipt.html', reservation=reservation, user=current_user)
    pdf = pdfkit.from_string(html, False)
    
    # Create response
    response = send_file(
        io.BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'receipt_{reservation.id}.pdf'
    )
    
    return response

# User Profile
@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        user = current_user
        user.name = request.form['name']
        user.email = request.form['email']
        user.phone = request.form['phone']
        
        # Update password if provided
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        if current_password and new_password:
            if user.check_password(current_password):
                user.set_password(new_password)
            else:
                flash('Current password is incorrect!', 'danger')
                return redirect(url_for('user.profile'))
        
        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('user.profile'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')
    
    return render_template('user/profile.html')

@user_bp.route('/reservations/<int:reservation_id>/complete', methods=['POST'])
@login_required
def complete_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    
    if reservation.user_id != current_user.id:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('user.history'))
    
    if reservation.status != 'active':
        flash('Only active reservations can be completed!', 'danger')
        return redirect(url_for('user.history'))
    
    try:
        # Calculate the total cost based on the time slot price
        reservation.total_cost = reservation.time_slot.price
        reservation.status = 'completed'
        
        # Update the spot status to available
        reservation.spot.status = 'A'
        
        # Update total revenue in admin dashboard
        admin = User.query.filter_by(user_type='admin').first()
        if admin:
            admin.total_revenue = (admin.total_revenue or 0) + reservation.total_cost
        
        db.session.commit()
        flash('Reservation completed successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error completing reservation: {str(e)}', 'danger')
    
    return redirect(url_for('user.history'))
