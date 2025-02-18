# Snooker Manager

A Flask-based web application for managing a snooker club, including game tracking, customer management, and financial reporting.

## Features

- User authentication with different roles (Admin, Ayoub, Ayman)
- Real-time game tracking
- Customer loan management
- Daily financial reports
- Activity logging
- Top customers tracking

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/snooker_manager.git
cd snooker_manager
```

2. Create a virtual environment and activate it:
```bash
# Windows
python -m venv venv
venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with these settings:
```
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///snooker.db
FLASK_ENV=development
```

5. Initialize the database:
```bash
# Windows
python app.py
```

## Usage

1. Run the application:
```bash
python app.py
```

2. Access the application at `http://localhost:5000`

3. Default login credentials:
- Admin: 
  - Username: `admin`
  - Password: `admin753159`
- Ayoub:
  - Username: `ayoub`
  - Password: `ayoub54321`
- Ayman:
  - Username: `ayman`
  - Password: `ayman12345`

## Features

### Admin Dashboard
- View all active games
- Generate daily reports
- Track customer loans
- View top paying customers
- Monitor user activity

### User Dashboard (Ayoub/Ayman)
- Manage assigned tables
- Start/end games
- Track customer payments
- View daily statistics

## License

MIT License
