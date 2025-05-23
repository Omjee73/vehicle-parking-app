from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from models import Admin, RegularUser, ParkingLot, ParkingSpot, Reservation, db, TimeSlot, User
from datetime import datetime, timedelta, date
from sqlalchemy import func, case
import io
import pdfkit

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
@login_required
def before_request():
    if not isinstance(current_user, Admin):
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('auth.login'))

# Admin Dashboard
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    if not isinstance(current_user, Admin):
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('user.dashboard'))
    
    # Get total users
    total_users = RegularUser.query.count()
    
    # Get total spots and occupied spots
    total_spots = ParkingSpot.query.count()
    occupied_spots = ParkingSpot.query.filter_by(status='O').count()
    
    # Get completed and released slots
    completed_slots = Reservation.query.filter_by(status='completed').count()
    released_slots = Reservation.query.filter_by(status='R').count()
    
    # Get total revenue
    total_revenue = db.session.query(func.sum(Reservation.total_cost)).filter(
        Reservation.status.in_(['completed', 'R'])
    ).scalar() or 0
    
    # Get recent reservations
    recent_reservations = Reservation.query.order_by(Reservation.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_spots=total_spots,
                         occupied_spots=occupied_spots,
                         completed_slots=completed_slots,
                         released_slots=released_slots,
                         total_revenue=total_revenue,
                         recent_reservations=recent_reservations)

# Parking Lots Management
@admin_bp.route('/lots')
def lots():
    lots = ParkingLot.query.all()
    return render_template('admin/lots.html', lots=lots)

@admin_bp.route('/lots/create', methods=['GET', 'POST'])
def create_lot():
    if request.method == 'POST':
        # Create the parking lot
        lot = ParkingLot(
            name=request.form['name'],
            prime_location_name=request.form['prime_location_name'],
            address=request.form['address'],
            pin_code=request.form['pin_code'],
            price_per_hour=float(request.form['price_per_hour']),
            maximum_spots=int(request.form['maximum_spots'])
        )
        db.session.add(lot)
        db.session.commit()
        
        # Create parking spots
        for i in range(1, lot.maximum_spots + 1):
            spot = ParkingSpot(
                lot_id=lot.id,
                spot_number=f"{lot.name}-{i:03d}",
                status='A'
            )
            db.session.add(spot)
        
        # Create time slots (30-minute intervals)
        start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
        end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()
        slot_price = lot.price_per_hour / 2  # Price for 30 minutes
        
        current_time = start_time
        while current_time < end_time:
            slot_end = (datetime.combine(datetime.today(), current_time) + timedelta(minutes=30)).time()
            if slot_end > end_time:
                break
                
            time_slot = TimeSlot(
                lot_id=lot.id,
                start_time=current_time,
                end_time=slot_end,
                price=slot_price
            )
            db.session.add(time_slot)
            current_time = slot_end
        
        db.session.commit()
        flash('Parking lot created successfully!', 'success')
        return redirect(url_for('admin.lots'))
    
    return render_template('admin/create_lot.html')

@admin_bp.route('/lots/<int:lot_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_lot(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    
    if request.method == 'POST':
        # Update basic lot information
        lot.name = request.form['name']
        lot.prime_location_name = request.form['prime_location_name']
        lot.address = request.form['address']
        lot.pin_code = request.form['pin_code']
        lot.price_per_hour = float(request.form['price_per_hour'])
        
        # Get new time slots
        start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
        end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()
        
        # Calculate number of 30-minute slots
        start_dt = datetime.combine(datetime.today(), start_time)
        end_dt = datetime.combine(datetime.today(), end_time)
        diff_mins = int((end_dt - start_dt).total_seconds() / 60)
        num_slots = diff_mins // 30
        
        # Delete existing time slots
        TimeSlot.query.filter_by(lot_id=lot.id).delete()
        
        # Create new time slots
        current_time = start_dt
        for i in range(num_slots):
            slot_end = current_time + timedelta(minutes=30)
            time_slot = TimeSlot(
                lot_id=lot.id,
                start_time=current_time.time(),
                end_time=slot_end.time(),
                price=lot.price_per_hour / 2  # Price for 30 minutes
            )
            db.session.add(time_slot)
            current_time = slot_end
        
        # Update maximum spots based on number of slots
        lot.maximum_spots = num_slots
        
        try:
            db.session.commit()
            flash('Parking lot updated successfully!', 'success')
            return redirect(url_for('admin.lots'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating parking lot: {str(e)}', 'danger')
    
    return render_template('admin/edit_lot.html', lot=lot)

@admin_bp.route('/lots/<int:lot_id>/delete', methods=['POST'])
def delete_lot(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    
    try:
        # First, delete all reservations associated with spots in this lot
        for spot in lot.spots:
            Reservation.query.filter_by(spot_id=spot.id).delete()
        
        # Then delete all spots in the lot
        ParkingSpot.query.filter_by(lot_id=lot_id).delete()
        
        # Delete all time slots for the lot
        TimeSlot.query.filter_by(lot_id=lot_id).delete()
        
        # Finally delete the lot itself
        db.session.delete(lot)
        db.session.commit()
        
        flash('Parking lot deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting parking lot: {str(e)}', 'danger')
    
    return redirect(url_for('admin.lots'))

@admin_bp.route('/lots/<int:lot_id>/slots')
@login_required
def view_slots(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    time_slots = TimeSlot.query.filter_by(lot_id=lot_id).order_by(TimeSlot.start_time).all()
    
    # Get selected date from query params, default to today
    selected_date = request.args.get('date')
    if selected_date:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    else:
        selected_date = datetime.now().date()
    
    # For each time slot, gather all reservations for the selected date
    slot_statuses = []
    for slot in time_slots:
        reservations = Reservation.query.filter_by(
            date=selected_date,
            time_slot_id=slot.id,
            status='active'
        ).all()
        slot_statuses.append({
            'slot': slot,
            'reservations': reservations
        })
    
    return render_template('admin/view_slots.html',
                           lot=lot,
                           slot_statuses=slot_statuses,
                           selected_date=selected_date)

# Users Management
@admin_bp.route('/users')
def users():
    users = RegularUser.query.all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/<int:user_id>/toggle-block', methods=['POST'])
def toggle_block_user(user_id):
    user = RegularUser.query.get_or_404(user_id)
    user.is_blocked = not user.is_blocked
    db.session.commit()
    
    status = 'blocked' if user.is_blocked else 'unblocked'
    flash(f'User {status} successfully!', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/history')
def user_history(user_id):
    user = RegularUser.query.get_or_404(user_id)
    reservations = Reservation.query.filter_by(user_id=user_id).order_by(Reservation.created_at.desc()).all()
    return render_template('admin/user_history.html', user=user, reservations=reservations)

# Admin Summary
@admin_bp.route('/summary')
@login_required
def summary():
    # Get total users
    total_users = RegularUser.query.count()
    
    # Get total lots and spots
    total_lots = ParkingLot.query.count()
    total_spots = ParkingSpot.query.count()
    
    # Get active reservations
    active_reservations = Reservation.query.filter_by(status='active').count()
    
    # Get lot-wise summary
    lot_summary = []
    lots = ParkingLot.query.all()
    for lot in lots:
        total_spots = len(lot.spots)
        occupied_spots = len([spot for spot in lot.spots if spot.status == 'O'])
        available_spots = total_spots - occupied_spots
        lot_summary.append({
            'name': lot.name,
            'total_spots': total_spots,
            'occupied_spots': occupied_spots,
            'available_spots': available_spots
        })
    
    # Get occupancy data for each lot
    occupancy_data = []
    occupancy_labels = []
    for lot in lots:
        total_spots = len(lot.spots)
        occupied_spots = len([spot for spot in lot.spots if spot.status == 'O'])
        occupancy_rate = (occupied_spots / total_spots * 100) if total_spots > 0 else 0
        occupancy_data.append(round(occupancy_rate, 1))
        occupancy_labels.append(lot.name)
    
    # Get revenue data for the last 7 days
    revenue_data = []
    revenue_labels = []
    today = date.today()
    
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day, datetime.max.time())
        
        # Calculate revenue for the day
        daily_revenue = db.session.query(func.sum(Reservation.total_cost))\
            .filter(Reservation.created_at.between(day_start, day_end))\
            .scalar() or 0
        
        revenue_data.append(float(daily_revenue))
        revenue_labels.append(day.strftime('%Y-%m-%d'))
    
    return render_template('admin/summary.html',
                         total_users=total_users,
                         total_lots=total_lots,
                         total_spots=total_spots,
                         active_reservations=active_reservations,
                         lot_summary=lot_summary,
                         occupancy_data=occupancy_data,
                         occupancy_labels=occupancy_labels,
                         revenue_data=revenue_data,
                         revenue_labels=revenue_labels)

# Admin Profile
@admin_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        admin = current_user
        admin.name = request.form['name']
        admin.email = request.form['email']
        
        # Update password if provided
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        if current_password and new_password:
            if admin.check_password(current_password):
                admin.set_password(new_password)
            else:
                flash('Current password is incorrect!', 'danger')
                return redirect(url_for('admin.profile'))
        
        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('admin.profile'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')
    
    return render_template('admin/profile.html')

@admin_bp.route('/reservations/<int:reservation_id>/complete', methods=['POST'])
@login_required
def complete_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    
    if reservation.status != 'active':
        flash('Only active reservations can be completed!', 'danger')
        return redirect(url_for('admin.user_history', user_id=reservation.user_id))
    
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
    
    return redirect(url_for('admin.user_history', user_id=reservation.user_id))

@admin_bp.route('/reservations/<int:reservation_id>/release', methods=['POST'])
@login_required
def release_spot(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    
    if reservation.status != 'active':
        flash('Only active reservations can be released!', 'danger')
        return redirect(url_for('admin.user_history', user_id=reservation.user_id))
    
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
    
    return redirect(url_for('admin.user_history', user_id=reservation.user_id))

@admin_bp.route('/reservations/<int:reservation_id>/receipt')
@login_required
def generate_receipt(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    return render_template('admin/receipt.html', reservation=reservation)

@admin_bp.route('/reservations/<int:reservation_id>/download_receipt')
@login_required
def download_receipt(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    
    # Generate PDF
    html = render_template('admin/receipt.html', reservation=reservation)
    pdf = pdfkit.from_string(html, False)
    
    # Create response
    response = send_file(
        io.BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'receipt_{reservation.id}.pdf'
    )
    
    return response
