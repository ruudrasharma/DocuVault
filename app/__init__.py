# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth
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

# OAuth config
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', '')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

# Initialize OAuth
oauth = OAuth(app)
google_oauth = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# Import blueprints
from .main import main_bp
from .auth import auth_bp

app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)

# Import models and initialize database
with app.app_context():
    from .database import User, PendingAccount
    db.create_all()
    # Migrate: add new columns if they don't exist (SQLite ALTER TABLE)
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            for col, definition in [
                ('oauth_provider', "VARCHAR(20) NOT NULL DEFAULT 'local'"),
                ('google_id',      'VARCHAR(100)'),
                ('google_email',   'VARCHAR(120)'),
                ('google_name',    'VARCHAR(120)'),
                ('google_avatar',  'VARCHAR(500)'),
            ]:
                try:
                    conn.execute(text(f'ALTER TABLE user ADD COLUMN {col} {definition}'))
                    conn.commit()
                    logger.info(f'Migrated: added column user.{col}')
                except Exception:
                    pass  # Column already exists
    except Exception as e:
        logger.warning(f'Migration check skipped: {e}')

@login_manager.user_loader
def load_user(user_id):
    from .database import User
    return User.query.get(int(user_id))