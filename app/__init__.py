# app/__init__.py
import os
import sys
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ── App factory ────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── Secret key — refuse to start in production with a weak/missing key ─────────
_SECRET_KEY = os.environ.get('SECRET_KEY', '')
_KNOWN_WEAK_KEYS = {
    '', 'your-secret-key', 'secret', 'changeme', 'dev', 'development',
    'flask-secret', 'mysecret', 'insecure',
}
_APP_ENV = os.environ.get('APP_ENV', 'development').lower()

if _APP_ENV == 'production' and _SECRET_KEY.lower() in _KNOWN_WEAK_KEYS:
    logger.critical(
        "FATAL: APP_ENV=production but SECRET_KEY is unset or a known placeholder. "
        "Set a strong SECRET_KEY environment variable before starting in production."
    )
    sys.exit(1)

app.config['SECRET_KEY'] = _SECRET_KEY or 'dev-only-insecure-key'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///site.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'data')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ── Session cookie security ─────────────────────────────────────────────────────
# Default True in production; local dev sets COOKIE_SECURE=false in .env
_COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'true' if _APP_ENV == 'production' else 'false').lower() == 'true'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = _COOKIE_SECURE
app.config['SESSION_COOKIE_HTTPONLY'] = True

# ── OAuth config ───────────────────────────────────────────────────────────────
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', '')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '')

# ── WTF CSRF ───────────────────────────────────────────────────────────────────
app.config['WTF_CSRF_ENABLED'] = os.environ.get('WTF_CSRF_ENABLED', 'true').lower() == 'true'
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour token validity

# ── DB / Login ─────────────────────────────────────────────────────────────────
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

# ── ProxyFix: trust X-Forwarded-Proto/Host from Nginx ─────────────────────────
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_prefix=1)

# ── CSRF Protection ────────────────────────────────────────────────────────────
try:
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)
    logger.info("CSRF protection enabled")
except ImportError:
    csrf = None
    logger.warning("Flask-WTF not installed — CSRF protection disabled. Run: pip install Flask-WTF")

# ── Rate Limiting ──────────────────────────────────────────────────────────────
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[],           # no global limit — apply per-route
        storage_uri="memory://",
    )
    logger.info("Rate limiting enabled")
except ImportError:
    limiter = None
    logger.warning("Flask-Limiter not installed — rate limiting disabled. Run: pip install Flask-Limiter")

# ── OAuth ──────────────────────────────────────────────────────────────────────
oauth = OAuth(app)
google_oauth = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# ── Import & register blueprints ───────────────────────────────────────────────
from .main import main_bp
from .auth import auth_bp
from .routes_wallet import wallet_bp
from .routes_citizen import citizen_bp

app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(wallet_bp)
app.register_blueprint(citizen_bp)

# ── DB initialisation + column migrations ─────────────────────────────────────
with app.app_context():
    from .database import User, PendingAccount
    db.create_all()
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

            for col, definition in [
                ('pqc_public_key', 'BLOB'),
                ('pqc_encrypted_private_key', 'BLOB'),
            ]:
                try:
                    conn.execute(text(f'ALTER TABLE wallet_key ADD COLUMN {col} {definition}'))
                    conn.commit()
                    logger.info(f'Migrated: added column wallet_key.{col}')
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f'Migration check skipped: {e}')


@login_manager.user_loader
def load_user(user_id):
    from .database import User
    return User.query.get(int(user_id))