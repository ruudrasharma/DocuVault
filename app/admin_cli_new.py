from app import app, db
from app.database_models import User
import pyotp
import getpass
import time
from tabulate import tabulate

def main():
    with app.app_context():
        while True:
            print("\nSuper Admin Console")
            print("1. View users")
            print("2. Create new user")
            print("3. Reset password for user")
            print("4. Reset TOTP for user")
            print("5. Remove user")
            print("6. Exit")
            choice = input("Enter choice: ").strip()

            if choice == '1':
                users = User.query.all()
                if not users:
                    print("No users found.")
                    continue
                user_data = [[user.username, user.role, user.password_hash] for user in users]
                print("\nUsers:")
                print(tabulate(user_data, headers=["Username", "Role", "Hashed Password"], tablefmt="grid"))

            elif choice == '2':
                username = input("Enter username: ").strip()
                if User.query.filter_by(username=username).first():
                    print("User already exists.")
                    continue
                password = getpass.getpass("Enter password: ")
                role = input("Enter role (admin/institute/verifier): ").strip().lower()
                if role not in {'admin', 'institute', 'verifier'}:
                    print("Invalid role.")
                    continue
                user = User(username=username, role=role)
                user.set_password(password)
                totp_secret = user.generate_totp_secret()
                print(f"TOTP secret: {totp_secret}")
                print(f"Provisioning URI: {user.get_totp_uri()}")
                print("Please generate a TOTP code from this secret and enter it to confirm.")
                time.sleep(5)  # Allow time to generate code
                token = input("Enter TOTP code: ").strip()
                if user.verify_totp(token):
                    db.session.add(user)
                    db.session.commit()
                    print(f"User '{username}' created with role '{role}'.")
                else:
                    print("Invalid TOTP code. User creation failed.")

            elif choice == '3':
                username = input("Enter username: ").strip()
                user = User.query.filter_by(username=username).first()
                if not user:
                    print("User not found.")
                    continue
                password = getpass.getpass("Enter new password: ")
                user.set_password(password)
                db.session.commit()
                print(f"Password reset for '{username}'.")

            elif choice == '4':
                username = input("Enter username: ").strip()
                user = User.query.filter_by(username=username).first()
                if not user:
                    print("User not found.")
                    continue
                totp_secret = user.generate_totp_secret()
                print(f"New TOTP secret: {totp_secret}")
                print(f"Provisioning URI: {user.get_totp_uri()}")
                print("Please generate a TOTP code from this new secret and enter it to confirm.")
                time.sleep(5)  # Allow time to generate code
                token = input("Enter TOTP code: ").strip()
                if user.verify_totp(token):
                    db.session.commit()
                    print(f"TOTP reset for '{username}'.")
                else:
                    db.session.rollback()
                    print("Invalid TOTP code. TOTP reset failed.")

            elif choice == '5':
                username = input("Enter username: ").strip()
                user = User.query.filter_by(username=username).first()
                if not user:
                    print("User not found.")
                    continue
                confirm = input(f"Are you sure you want to remove user '{username}'? (y/n): ").strip().lower()
                if confirm == 'y':
                    db.session.delete(user)
                    db.session.commit()
                    print(f"User '{username}' removed.")
                else:
                    print("User removal canceled.")

            elif choice == '6':
                print("Exiting.")
                break
            else:
                print("Invalid choice.")

if __name__ == '__main__':
    main()