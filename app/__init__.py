# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
import logging
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Configure logging to terminal
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'data')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

# Import blueprints
from .main import main_bp
from .auth import auth_bp

app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)

# Import models and initialize database
with app.app_context():
    from .database_models import User, CertificateRecord, VerifiableCredential, AnalyticsLog
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    from .database_models import User
    return User.query.get(int(user_id))