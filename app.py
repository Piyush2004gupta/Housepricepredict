import os
import json
from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import PyPDF2
from docx import Document
from PIL import Image
import io
import base64
import stripe
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///portfolio_generator.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Stripe configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_your_stripe_key')

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_premium = db.Column(db.Boolean, default=False)
    portfolios = db.relationship('Portfolio', backref='user', lazy=True)

class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    template_id = db.Column(db.String(50), nullable=False)
    resume_data = db.Column(db.Text, nullable=False)  # JSON string
    custom_domain = db.Column(db.String(200))
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Utility functions
def extract_text_from_pdf(file):
    """Extract text from PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except:
        return None

def extract_text_from_docx(file):
    """Extract text from DOCX file"""
    try:
        doc = Document(file)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except:
        return None

def parse_resume_text(text):
    """Parse resume text and structure it"""
    # Basic parsing - in production, you'd use NLP libraries
    lines = text.split('\n')
    
    data = {
        'name': '',
        'email': '',
        'phone': '',
        'summary': '',
        'experience': [],
        'education': [],
        'skills': [],
        'projects': []
    }
    
    # Simple heuristic parsing
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        # Extract email
        if '@' in line and not data['email']:
            data['email'] = line
            
        # Extract phone
        if any(char.isdigit() for char in line) and len(line) >= 10 and len(line) <= 15:
            if not data['phone']:
                data['phone'] = line
                
        # First non-email, non-phone line is likely the name
        if not data['name'] and '@' not in line and not any(char.isdigit() for char in line):
            data['name'] = line
            
    return data

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))
        
        user = User(
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')
    
    return render_template('auth/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    portfolios = Portfolio.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', portfolios=portfolios)

@app.route('/create-portfolio', methods=['GET', 'POST'])
@login_required
def create_portfolio():
    if request.method == 'POST':
        title = request.form['title']
        template_id = request.form['template']
        
        # Handle file upload
        if 'resume' not in request.files:
            flash('No file selected')
            return redirect(request.url)
        
        file = request.files['resume']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        # Extract text from file
        text = None
        if file.filename.endswith('.pdf'):
            text = extract_text_from_pdf(file)
        elif file.filename.endswith('.docx'):
            text = extract_text_from_docx(file)
        elif file.filename.endswith('.txt'):
            text = file.read().decode('utf-8')
        
        if not text:
            flash('Could not extract text from file')
            return redirect(request.url)
        
        # Parse resume data
        resume_data = parse_resume_text(text)
        
        # Create portfolio
        portfolio = Portfolio(
            user_id=current_user.id,
            title=title,
            template_id=template_id,
            resume_data=json.dumps(resume_data)
        )
        db.session.add(portfolio)
        db.session.commit()
        
        flash('Portfolio created successfully!')
        return redirect(url_for('edit_portfolio', id=portfolio.id))
    
    templates = [
        {'id': 'modern', 'name': 'Modern Professional', 'preview': 'modern.png'},
        {'id': 'creative', 'name': 'Creative Design', 'preview': 'creative.png'},
        {'id': 'minimal', 'name': 'Minimal Clean', 'preview': 'minimal.png'},
        {'id': 'tech', 'name': 'Tech Focused', 'preview': 'tech.png'}
    ]
    
    return render_template('create_portfolio.html', templates=templates)

@app.route('/edit-portfolio/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_portfolio(id):
    portfolio = Portfolio.query.get_or_404(id)
    
    if portfolio.user_id != current_user.id:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        # Update portfolio data
        resume_data = json.loads(portfolio.resume_data)
        
        # Update fields from form
        resume_data['name'] = request.form.get('name', '')
        resume_data['email'] = request.form.get('email', '')
        resume_data['phone'] = request.form.get('phone', '')
        resume_data['summary'] = request.form.get('summary', '')
        
        portfolio.resume_data = json.dumps(resume_data)
        portfolio.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash('Portfolio updated successfully!')
        return redirect(url_for('preview_portfolio', id=id))
    
    resume_data = json.loads(portfolio.resume_data)
    return render_template('edit_portfolio.html', portfolio=portfolio, resume_data=resume_data)

@app.route('/preview/<int:id>')
def preview_portfolio(id):
    portfolio = Portfolio.query.get_or_404(id)
    resume_data = json.loads(portfolio.resume_data)
    
    # Show branding for free users
    show_branding = not portfolio.user.is_premium
    
    return render_template(f'templates/{portfolio.template_id}.html', 
                         resume_data=resume_data, 
                         show_branding=show_branding,
                         portfolio=portfolio)

@app.route('/portfolio/<int:id>')
def public_portfolio(id):
    portfolio = Portfolio.query.get_or_404(id)
    
    if not portfolio.is_published:
        return "Portfolio not found", 404
    
    resume_data = json.loads(portfolio.resume_data)
    show_branding = not portfolio.user.is_premium
    
    return render_template(f'templates/{portfolio.template_id}.html', 
                         resume_data=resume_data, 
                         show_branding=show_branding,
                         portfolio=portfolio)

@app.route('/upgrade')
@login_required
def upgrade():
    return render_template('upgrade.html')

@app.route('/create-payment-intent', methods=['POST'])
@login_required
def create_payment_intent():
    try:
        data = json.loads(request.data)
        
        # Create a PaymentIntent with the order amount and currency
        intent = stripe.PaymentIntent.create(
            amount=4900,  # ₹49 in paisa
            currency='inr',
            metadata={'user_id': current_user.id}
        )
        
        return jsonify({
            'client_secret': intent['client_secret']
        })
    except Exception as e:
        return jsonify(error=str(e)), 403

@app.route('/payment-success')
@login_required
def payment_success():
    # Upgrade user to premium
    current_user.is_premium = True
    db.session.commit()
    
    flash('Payment successful! You are now a premium user.')
    return redirect(url_for('dashboard'))

# API Routes
@app.route('/api/portfolios')
@login_required
def api_portfolios():
    portfolios = Portfolio.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': p.id,
        'title': p.title,
        'template_id': p.template_id,
        'created_at': p.created_at.isoformat(),
        'is_published': p.is_published
    } for p in portfolios])

# Initialize database
@app.before_first_request
def create_tables():
    db.create_all()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
