import sqlite3
import bcrypt
import pyotp
from pqc import pqc_encrypt

# Connect to the database
try:
    conn = sqlite3.connect('../users.db')  # Adjusted path for app/ directory
    c = conn.cursor()
except sqlite3.Error as e:
    print(f"Database connection error: {e}")
    exit(1)

# Ensure the users table has the correct schema
try:
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        password TEXT,
        role TEXT,
        totp_secret TEXT,
        totp_pub_key BLOB
    )''')
    conn.commit()
except sqlite3.Error as e:
    print(f"Schema creation error: {e}")
    conn.close()
    exit(1)

# Clear existing users to avoid duplicates
try:
    c.execute("DELETE FROM users")
    conn.commit()
except sqlite3.Error as e:
    print(f"Error clearing users table: {e}")

# Sample user data
users = [
    {
        'username': 'admin',
        'password': 'admin123',
        'role': 'admin'
    },
    {
        'username': 'institute1',
        'password': 'instpass',
        'role': 'institution'
    },
    {
        'username': 'verifier1',
        'password': 'verify123',
        'role': 'verifier'
    }
]

# Insert users into the database
for user in users:
    try:
        hashed_password = bcrypt.hashpw(user['password'].encode('utf-8'), bcrypt.gensalt())
        secret = pyotp.random_base32()
        encrypted_secret, pub_key = pqc_encrypt(secret)
        c.execute(
            "INSERT INTO users (username, password, role, totp_secret, totp_pub_key) VALUES (?, ?, ?, ?, ?)",
            (user['username'], hashed_password, user['role'], encrypted_secret, pub_key)
        )
        print(f"Added user: {user['username']} (Role: {user['role']})")
    except sqlite3.Error as e:
        print(f"Error inserting user {user['username']}: {e}")
    except Exception as e:
        print(f"Unexpected error for user {user['username']}: {e}")

# Commit changes and close connection
conn.commit()
conn.close()

print("\nUsers added successfully. Use the following credentials:")
for user in users:
    print(f"Username: {user['username']}, Password: {user['password']}, Role: {user['role']}")
print("Note: TOTP secrets are encrypted. Use /admin/add_user or /admin/recover_2fa to obtain QR codes for 2FA setup.")