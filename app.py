from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import os
from io import BytesIO
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table as ReportTable, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Database configuration
if os.getenv('RAILWAY_ENVIRONMENT'):
    # Use PostgreSQL on Railway
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
else:
    # Use SQLite locally
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///snooker.db'

# Fix PostgreSQL URL if necessary
if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'ayoub', 'ayman'
    activities = db.relationship('UserActivity', backref='user', lazy=True)

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    owner = db.Column(db.String(20), nullable=False)  # 'ayoub' or 'ayman'

class GameRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
    end_time = db.Column(db.DateTime)
    price = db.Column(db.Float, nullable=False, default=0)
    payment_status = db.Column(db.String(20), nullable=False, default='loan')
    state = db.Column(db.String(20), nullable=False, default='inprogress')
    customer_name = db.Column(db.String(100))
    created_by = db.Column(db.String(80), nullable=False)
    confirmed = db.Column(db.Boolean, default=False)
    archived = db.Column(db.Boolean, default=False)

class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    details = db.Column(db.String(500))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def init_db():
    with app.app_context():
        db.drop_all()  # Reset the database
        db.create_all()
        print("Database created successfully")

        # Create users
        users = [
            User(username='admin', password_hash=generate_password_hash('admin753159'), role='admin'),
            User(username='ayoub', password_hash=generate_password_hash('ayoub54321'), role='ayoub'),
            User(username='ayman', password_hash=generate_password_hash('ayman12345'), role='ayman')
        ]
        db.session.add_all(users)
        print("Users created")

        # Create tables
        tables = [
            Table(name='mini 1', owner='ayoub'),
            Table(name='mini 2', owner='ayoub'),
            Table(name='strong', owner='ayman'),
            Table(name='magnum', owner='ayman')
        ]
        db.session.add_all(tables)
        print("Tables created")
        
        db.session.commit()
        print("Database initialized successfully")

def log_user_activity(user, action, details=None):
    """Log user activity to the database"""
    activity = UserActivity(
        user_id=user.id,
        action=action,
        details=details
    )
    db.session.add(activity)
    db.session.commit()

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        print(f"Login attempt - Username: {username}")
        
        user = User.query.filter_by(username=username).first()
        print(f"User found: {user is not None}")
        
        if user and check_password_hash(user.password_hash, password):
            print(f"Password match for user: {username}")
            login_user(user)
            log_user_activity(user, 'Logged in')
            print(f"User logged in successfully: {username}")
            flash(f'Welcome {user.username}!', 'success')
            return redirect(url_for('user_dashboard'))
        
        print("Invalid login attempt")
        flash('Invalid username or password. Please try again.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    log_user_activity(current_user, 'Logged out')
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def user_dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    tables = Table.query.filter_by(owner=current_user.username).all()
    records = GameRecord.query.join(Table).filter(Table.owner == current_user.username, GameRecord.archived == False).all()
    total_paid, total_loan, customer_stats = get_user_totals(current_user.username)
    
    return render_template('user_dashboard.html', 
                         tables=tables, 
                         records=records,
                         total_paid=total_paid,
                         total_loan=total_loan,
                         customer_stats=customer_stats)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Unauthorized access.')
        return redirect(url_for('user_dashboard'))
    
    # Only get Ayoub and Ayman users
    users = User.query.filter(User.role.in_(['ayoub', 'ayman'])).all()
    user_stats = {}
    customer_loans = []
    top_customers = []
    
    for user in users:
        total_paid, total_loan, customer_stats = get_user_totals(user.username)
        user_stats[user.username] = {
            'total_paid': total_paid,
            'total_loan': total_loan,
            'customer_stats': customer_stats
        }
        
        # Get customer loans for this user
        for customer, stats in customer_stats.items():
            if stats['loan'] > 0:
                # Get last activity for this customer
                last_record = GameRecord.query.join(Table).filter(
                    Table.owner == user.username,
                    GameRecord.customer_name == customer,
                    GameRecord.archived == False
                ).order_by(GameRecord.start_time.desc()).first()
                
                customer_loans.append({
                    'name': customer,
                    'total_loan': stats['loan'],
                    'last_activity': last_record.start_time if last_record else datetime.now(),
                    'owner': user.username
                })
        
        # Get top paying customers for this user
        for customer, stats in customer_stats.items():
            if stats['paid'] > 0:
                # Get last activity for this customer
                last_record = GameRecord.query.join(Table).filter(
                    Table.owner == user.username,
                    GameRecord.customer_name == customer,
                    GameRecord.archived == False
                ).order_by(GameRecord.start_time.desc()).first()
                
                top_customers.append({
                    'name': customer,
                    'total_paid': stats['paid'],
                    'last_activity': last_record.start_time if last_record else datetime.now(),
                    'owner': user.username
                })
    
    # Sort customer loans by total loan amount (descending)
    customer_loans = sorted(customer_loans, key=lambda x: x['total_loan'], reverse=True)
    
    # Sort top customers by total paid amount (descending) and get top 10
    top_customers = sorted(top_customers, key=lambda x: x['total_paid'], reverse=True)[:10]
    
    # Get recent activity logs for all users
    recent_activities = UserActivity.query.join(User).order_by(
        UserActivity.timestamp.desc()
    ).limit(50).all()
    
    # Group activities by user
    user_activities = {}
    for user in users + [User.query.filter_by(role='admin').first()]:
        user_activities[user.username] = UserActivity.query.filter_by(
            user_id=user.id
        ).order_by(UserActivity.timestamp.desc()).limit(20).all()
    
    return render_template('admin_dashboard.html', 
                         users=users, 
                         user_stats=user_stats,
                         customer_loans=customer_loans,
                         top_customers=top_customers,
                         recent_activities=recent_activities,
                         user_activities=user_activities)

@app.route('/admin/invoice/<username>/<customer_name>')
@login_required
def generate_invoice(username, customer_name):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get all records for this customer
    records = GameRecord.query.join(Table).filter(
        Table.owner == username,
        GameRecord.customer_name == customer_name,
        GameRecord.confirmed == True,
        GameRecord.archived == False
    ).order_by(GameRecord.start_time.desc()).all()
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Title
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"Invoice for {customer_name}", styles['Title']))
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    
    # Table data
    data = [['Date', 'Table', 'Duration', 'Price', 'Status']]
    total_paid = 0
    total_loan = 0
    
    for record in records:
        if record.end_time:  # Only include finished games
            duration = record.end_time - record.start_time
            hours = duration.total_seconds() / 3600
            
            data.append([
                record.start_time.strftime('%Y-%m-%d %H:%M'),
                Table.query.get(record.table_id).name,
                f"{hours:.1f} hours",
                f"{record.price:.2f} MAD",
                record.payment_status
            ])
            
            if record.payment_status == 'paid':
                total_paid += record.price
            else:
                total_loan += record.price
    
    # Add totals
    data.append(['', '', '', 'Total Paid:', f"{total_paid:.2f} MAD"])
    data.append(['', '', '', 'Total Loan:', f"{total_loan:.2f} MAD"])
    
    # Create table
    table = ReportTable(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -2), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'invoice_{username}_{customer_name}_{datetime.now().strftime("%Y%m%d")}.pdf',
        mimetype='application/pdf'
    )

@app.route('/api/active_games')
@login_required
def get_active_games():
    if current_user.role != 'admin':
        # Regular users only see their own games
        games = GameRecord.query.join(Table).filter(
            Table.owner == current_user.username,
            GameRecord.state == 'inprogress'
        ).all()
    else:
        # Admins see all active games
        games = GameRecord.query.filter_by(state='inprogress').all()
    
    active_games = []
    for game in games:
        table = Table.query.get(game.table_id)
        duration = datetime.now() - game.start_time
        hours = duration.total_seconds() / 3600
        
        active_games.append({
            'id': game.id,
            'table_name': table.name,
            'table_owner': table.owner,
            'start_time': game.start_time.strftime('%Y-%m-%d %H:%M'),
            'duration': f"{hours:.1f} hours",
            'price': f"{game.price:.2f} MAD"
        })
    
    return jsonify(active_games)

@app.route('/record/new', methods=['POST'])
@login_required
def new_record():
    table_id = request.form.get('table_id')
    if not table_id:
        return jsonify({'error': 'No table specified'}), 400
        
    # Check if table already has an active game
    active_game = GameRecord.query.filter_by(
        table_id=table_id,
        state='inprogress'
    ).first()
    
    if active_game:
        return jsonify({'error': 'Table already has an active game'}), 400
    
    record = GameRecord(
        table_id=table_id,
        start_time=datetime.now(),
        price=0.0,
        created_by=current_user.username
    )
    
    db.session.add(record)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/record/update/<int:record_id>', methods=['POST'])
@login_required
def update_record(record_id):
    record = GameRecord.query.get_or_404(record_id)
    
    # Check if record is already confirmed
    if record.confirmed:
        return jsonify({'success': False, 'error': 'Record is already confirmed'}), 400
    
    # End game
    if 'end_game' in request.form:
        record.end_time = datetime.now()
        record.state = 'finished'
        db.session.commit()
        return jsonify({'success': True})
    
    # Update price
    if 'price' in request.form:
        try:
            record.price = float(request.form['price'])
            db.session.commit()
            return jsonify({'success': True})
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid price'}), 400
    
    # Update customer name
    if 'customer_name' in request.form:
        record.customer_name = request.form['customer_name']
    
    # Update payment status
    if 'payment_status' in request.form:
        record.payment_status = request.form['payment_status']
        # If marking as paid, also confirm the record
        if record.payment_status == 'paid':
            record.confirmed = True
    
    # Confirm record
    if 'confirm' in request.form:
        if not record.customer_name:
            return jsonify({'success': False, 'error': 'Customer name is required'}), 400
        record.confirmed = True
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/get_price/<int:record_id>')
@login_required
def get_current_price(record_id):
    record = GameRecord.query.get_or_404(record_id)
    return jsonify({
        'price': record.price,
        'duration': str(datetime.now() - record.start_time).split('.')[0]  # Format as HH:MM:SS
    })

@app.route('/record/delete/<int:id>', methods=['POST'])
@login_required
def delete_record(id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    record = GameRecord.query.get_or_404(id)
    db.session.delete(record)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/pay_loan', methods=['POST'])
@login_required
def pay_loan():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        customer_name = data.get('customer_name')
        owner = data.get('owner')
        amount = float(data.get('amount', 0))
        
        if not all([customer_name, owner, amount]):
            return jsonify({'error': 'Missing required fields'}), 400
            
        # Get all loan records for this customer
        loan_records = GameRecord.query.join(Table).filter(
            Table.owner == owner,
            GameRecord.customer_name == customer_name,
            GameRecord.payment_status == 'loan',
            GameRecord.archived == False
        ).order_by(GameRecord.start_time).all()
        
        remaining_amount = amount
        for record in loan_records:
            if remaining_amount <= 0:
                break
                
            if remaining_amount >= record.price:
                record.payment_status = 'paid'
                remaining_amount -= record.price
            else:
                # Split the record into paid and loan parts
                new_record = GameRecord(
                    table_id=record.table_id,
                    start_time=record.start_time,
                    end_time=record.end_time,
                    price=remaining_amount,
                    payment_status='paid',
                    state='finished',
                    customer_name=record.customer_name,
                    created_by=current_user.username,
                    confirmed=True
                )
                record.price -= remaining_amount
                db.session.add(new_record)
                remaining_amount = 0
        
        db.session.commit()
        log_user_activity(current_user, 'Processed loan payment', 
                         f'Customer: {customer_name}, Owner: {owner}, ' +
                         f'Amount: {amount}')
        return jsonify({'message': 'Loan payment processed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/start_game', methods=['POST'])
@login_required
def start_game():
    try:
        data = request.get_json()
        table_id = data.get('table_id')
        customer_name = data.get('customer_name')
        
        if not table_id or not customer_name:
            return jsonify({'error': 'Missing required fields'}), 400
            
        table = Table.query.get(table_id)
        if not table:
            return jsonify({'error': 'Table not found'}), 404
            
        if table.state == 'occupied':
            return jsonify({'error': 'Table is already occupied'}), 400
            
        game = GameRecord(
            table_id=table_id,
            start_time=datetime.now(),
            customer_name=customer_name,
            created_by=current_user.username
        )
        table.state = 'occupied'
        
        db.session.add(game)
        db.session.commit()
        
        log_user_activity(current_user, 'Started game', 
                         f'Table: {table.name}, Customer: {customer_name}')
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/end_game', methods=['POST'])
@login_required
def end_game():
    try:
        data = request.get_json()
        table_id = data.get('table_id')
        payment_status = data.get('payment_status', 'paid')
        
        if not table_id:
            return jsonify({'error': 'Missing table_id'}), 400
            
        table = Table.query.get(table_id)
        if not table:
            return jsonify({'error': 'Table not found'}), 404
            
        game = GameRecord.query.filter_by(
            table_id=table_id,
            state='active'
        ).first()
        
        if not game:
            return jsonify({'error': 'No active game found for this table'}), 404
            
        game.end_time = datetime.now()
        game.state = 'finished'
        game.payment_status = payment_status
        game.price = calculate_price(game.start_time, game.end_time)
        table.state = 'available'
        
        db.session.commit()
        
        log_user_activity(current_user, 'Ended game', 
                         f'Table: {table.name}, Customer: {game.customer_name}, ' +
                         f'Price: {game.price}, Payment: {payment_status}')
        
        return jsonify({
            'success': True,
            'price': game.price
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/confirm_game/<int:game_id>', methods=['POST'])
@login_required
def confirm_game(game_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    game = GameRecord.query.get_or_404(game_id)
    game.confirmed = True
    db.session.commit()
    
    log_user_activity(current_user, 'Confirmed game', 
                     f'Game ID: {game_id}, Customer: {game.customer_name}, ' +
                     f'Price: {game.price}')
    
    return jsonify({'success': True})

def get_user_totals(owner):
    """Calculate total paid and loan amounts for a user's tables"""
    records = GameRecord.query.join(Table).filter(
        Table.owner == owner,
        GameRecord.confirmed == True,
        GameRecord.archived == False
    ).all()
    
    total_paid = 0
    total_loan = 0
    customer_stats = {}

    for record in records:
        if record.payment_status == 'paid':
            total_paid += record.price
        else:
            total_loan += record.price
        
        # Update customer stats
        if record.customer_name not in customer_stats:
            customer_stats[record.customer_name] = {'paid': 0, 'loan': 0}
        
        if record.payment_status == 'paid':
            customer_stats[record.customer_name]['paid'] += record.price
        else:
            customer_stats[record.customer_name]['loan'] += record.price

    return total_paid, total_loan, customer_stats

def generate_daily_invoice(owner, date):
    """Generate invoice for a specific owner and date"""
    # Get all confirmed records for the specified owner and date
    records = GameRecord.query.join(Table).filter(
        Table.owner == owner,
        GameRecord.confirmed == True,
        GameRecord.archived == False,
        db.func.date(GameRecord.start_time) == date
    ).all()

    # Create a BytesIO buffer to store the PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Add title
    styles = getSampleStyleSheet()
    title = Paragraph(f"Daily Report - {owner.capitalize()} - {date.strftime('%Y-%m-%d')}", styles['Title'])
    elements.append(title)

    # Prepare data for the table
    data = [['Table', 'Customer', 'Start Time', 'End Time', 'Duration', 'Price', 'Status']]
    total_paid = 0
    total_loan = 0

    # Add records to data
    for record in records:
        table = Table.query.get(record.table_id)
        duration = record.end_time - record.start_time if record.end_time else datetime.now() - record.start_time
        duration_str = str(duration).split('.')[0]  # Remove microseconds
        
        data.append([
            table.name,
            record.customer_name,
            record.start_time.strftime('%H:%M'),
            record.end_time.strftime('%H:%M') if record.end_time else 'In Progress',
            duration_str,
            f"{record.price:.2f} MAD",
            record.payment_status.capitalize()
        ])

        if record.payment_status == 'paid':
            total_paid += record.price
        else:
            total_loan += record.price

    # Add summary row
    data.append(['', '', '', '', '', '', ''])
    data.append(['Total Paid:', f"{total_paid:.2f} MAD", '', '', '', '', ''])
    data.append(['Total Loan:', f"{total_loan:.2f} MAD", '', '', '', '', ''])
    data.append(['Total:', f"{(total_paid + total_loan):.2f} MAD", '', '', '', '', ''])

    # Create table
    table = ReportTable(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -4), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, -4), (-1, -1), colors.black),
        ('FONTNAME', (0, -4), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -4), (-1, -1), 12),
        ('ALIGN', (0, -4), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

@app.route('/admin/daily_invoice/<owner>')
@login_required
def generate_daily_owner_invoice(owner):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    date = datetime.now()
    buffer = generate_daily_invoice(owner, date)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'daily_invoice_{owner}_{date.strftime("%Y%m%d")}.pdf',
        mimetype='application/pdf'
    )

@app.route('/admin/daily_invoice/all')
@login_required
def generate_daily_all_invoice():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    date = datetime.now()
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Title
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"Daily Report - All Workers", styles['Title']))
    elements.append(Paragraph(f"Date: {date.strftime('%Y-%m-%d')}", styles['Normal']))
    
    # Generate report for each worker
    total_all_paid = 0
    total_all_loan = 0
    
    for owner in ['ayoub', 'ayman']:
        elements.append(Paragraph(f"\n{owner.title()}'s Report", styles['Heading2']))
        
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        records = GameRecord.query.join(Table).filter(
            Table.owner == owner,
            GameRecord.confirmed == True,
            GameRecord.start_time >= start_of_day,
            GameRecord.start_time <= end_of_day,
            GameRecord.archived == False
        ).order_by(GameRecord.start_time.desc()).all()
        
        # Table data
        data = [['Time', 'Table', 'Customer', 'Duration', 'Price', 'Status']]
        total_paid = 0
        total_loan = 0
        
        for record in records:
            if record.end_time:
                duration = record.end_time - record.start_time
                hours = duration.total_seconds() / 3600
                
                data.append([
                    record.start_time.strftime('%H:%M'),
                    Table.query.get(record.table_id).name,
                    record.customer_name or 'N/A',
                    f"{hours:.1f} hours",
                    f"{record.price:.2f} MAD",
                    record.payment_status
                ])
                
                if record.payment_status == 'paid':
                    total_paid += record.price
                    total_all_paid += record.price
                else:
                    total_loan += record.price
                    total_all_loan += record.price
        
        # Add worker totals
        data.append(['', '', '', '', 'Total Paid:', f"{total_paid:.2f} MAD"])
        data.append(['', '', '', '', 'Total Loan:', f"{total_loan:.2f} MAD"])
        data.append(['', '', '', '', 'Total:', f"{(total_paid + total_loan):.2f} MAD"])
        
        # Create table
        table = ReportTable(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -3), (-1, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        elements.append(Paragraph("<br/><br/>", styles['Normal']))
    
    # Add grand total
    elements.append(Paragraph("Grand Total", styles['Heading1']))
    grand_total_data = [
        ['', 'Total Paid', 'Total Loan', 'Total'],
        ['All Workers', f"{total_all_paid:.2f} MAD", f"{total_all_loan:.2f} MAD", f"{(total_all_paid + total_all_loan):.2f} MAD"]
    ]
    
    grand_total_table = ReportTable(grand_total_data)
    grand_total_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(grand_total_table)
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'daily_invoice_all_{date.strftime("%Y%m%d")}.pdf',
        mimetype='application/pdf'
    )

@app.route('/admin/reset_day', methods=['POST'])
@login_required
def reset_day():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        # Get all confirmed records for the current day
        today = datetime.now().date()
        records = GameRecord.query.filter(
            GameRecord.confirmed == True,
            GameRecord.archived == False,
            db.func.date(GameRecord.start_time) == today
        ).all()

        # Archive the records
        for record in records:
            record.archived = True
        
        db.session.commit()
        return jsonify({'message': 'Day reset successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()  # Initialize the database
    print("Starting Flask application...")
    app.run(host='0.0.0.0', port=5000, debug=True)
