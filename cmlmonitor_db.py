import argparse
import pandas as pd
from flask import Flask
from extensions import db
from models import User, Config
from utils import safe_str, safe_int, safe_bool
from werkzeug.security import generate_password_hash


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cmlmonitor.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


def init_configs(username):
    with app.app_context():
        # 1. Verify the user exists to satisfy the Foreign Key constraint
        user = db.session.execute(db.select(User).filter_by(username=username)).scalar()
        if user is None:
            print(f"[-] Error: User '{username}' does not exist. Cannot set 'updated_by'.")
            return

        if not user.config_admin:
            print(f"[-] Error: User '{username}' is not allowed to manage CML Monitor configurations.")
            return
        # 2. Define the initial default configurations (matching your UI tabs)
        default_configs = [
            {'attr': 'init', 'value': '0'},
            # LDAP Defaults
            {'attr': 'ldap.enabled', 'value': '0'},
            {'attr': 'ldap.server', 'value': ''},
            {'attr': 'ldap.port', 'value': ''},
            {'attr': 'ldap.base_dn', 'value': ''},
            {'attr': 'ldap.bind_dn', 'value': ''},
            {'attr': 'ldap.bind_password', 'value': ''},

            # CML Defaults
            {'attr': 'cml.workspace_domain', 'value': ''},
            {'attr': 'cml.api_key', 'value': ''},
            {'attr': 'cml.namespace_prefix', 'value': ''},
            {'attr': 'cml.kubeconfig_path', 'value': ''},

            # Alert Defaults
            {'attr': 'alert.enabled', 'value': '0'},
            {'attr': 'alert.smtp.use_tls', 'value': '1'},
            {'attr': 'alert.smtp.server', 'value': ''},
            {'attr': 'alert.smtp.port', 'value': ''},
            {'attr': 'alert.smtp.user', 'value': ''},
            {'attr': 'alert.smtp.password', 'value': ''},
            {'attr': 'alert.smtp.alert_subject', 'value': 'ML Workbench Zombie Sessions Alert'},
            {'attr': 'alert.smtp.report_subject', 'value': 'ML Workbench Workload Report'},
            {'attr': 'alert.smtp.sender_email', 'value': ''},
            {'attr': 'alert.smtp.alert_recipient_emails', 'value': '[]'},
            {'attr': 'alert.smtp.report_recipient_emails', 'value': '[]'},
            {'attr': 'alert.runtime.alert_cron', 'value': ''},
            {'attr': 'alert.runtime.report_cron', 'value': ''}
        ]

        # 3. Iterate and insert only if they don't already exist
        added_count = 0
        for item in default_configs:
            existing_config = db.session.execute(db.select(Config).filter_by(attr=item['attr'])).scalar()

            if existing_config is None:
                new_conf = Config(attr=item['attr'], value=item['value'], updated_by=username)
                db.session.add(new_conf)
                print(f"  -> Inserted new config: {item['attr']}")
                added_count += 1
            else:
                print(f"  -> Config '{item['attr']}' already exists. Skipping.")

        # 4. Commit to the database
        try:
            if added_count > 0:
                db.session.commit()
                print(f"[+] Successfully seeded {added_count} new configurations.")
            else:
                print("[+] No new configurations needed seeding.")
        except Exception as e:
            db.session.rollback()
            print(f"[-] Database error while seeding configs: {e}")


def export_configs_to_csv(filename):
    with app.app_context():
        try:
            df = pd.read_sql(db.select(Config), con=db.engine)

            # Check if the DataFrame is empty (no users found)
            if df.empty:
                print("[-] No configs found in the database. Export cancelled.")
                return

            df.to_csv(filename, index=False, encoding='utf-8')        
            print(f"[+] Successfully exported {len(df)} configs to '{filename}'.")
        except Exception as e:
            print(f"[-] Error during pandas export: {e}")


def get_configs():
    # 1. Define the mapping: DB Attribute -> (Section, Dictionary Key, Cast Function)
    schema_mapping = {
        # SMTP
        'alert.enabled': ('smtp', 'smtp_enabled', safe_bool),
        'alert.smtp.use_tls': ('smtp', 'smtp_use_tls', safe_bool), # Cast to bool
        'alert.smtp.server': ('smtp', 'smtp_server', safe_str),
        'alert.smtp.port': ('smtp', 'smtp_port', safe_int),        # Cast to int
        'alert.smtp.user': ('smtp', 'smtp_user', safe_str),
        'alert.smtp.password': ('smtp', 'smtp_password', safe_str),
        'alert.smtp.alert_subject': ('smtp', 'smtp_alert_subject', safe_str),
        'alert.smtp.report_subject': ('smtp', 'smtp_report_subject', safe_str),
        'alert.smtp.sender_email': ('smtp', 'sender_email', safe_str),
        'alert.smtp.alert_recipient_emails': ('smtp', 'alert_recipient_emails', safe_str),
        'alert.smtp.report_recipient_emails': ('smtp', 'report_recipient_emails', safe_str),

        # CML API
        'cml.workspace_domain': ('cmlapi', 'WORKSPACE_DOMAIN', safe_str),
        'cml.api_key': ('cmlapi', 'API_KEY', safe_str),
        'cml.namespace_prefix': ('cmlapi', 'NAMESPACE_PREFIX', safe_str),
        'cml.kubeconfig_path': ('cmlapi', 'KUBECONFIG_PATH', safe_str),

        # LDAP
        'ldap.enabled': ('ldap', 'LDAP_ENABLED', safe_bool),
        'ldap.server': ('ldap', 'LDAP_SERVER', safe_str),
        'ldap.port': ('ldap', 'LDAP_PORT', safe_int),              # Cast to int
        'ldap.bind_dn': ('ldap', 'BIND_USER_DN', safe_str),
        'ldap.bind_password': ('ldap', 'BIND_USER_PASSWORD', safe_str),
        'ldap.base_dn': ('ldap', 'BASE_DN', safe_str),

        # Runtime
        'alert.runtime.alert_cron': ('runtime', 'alert_daemon', safe_str),
        'alert.runtime.report_cron': ('runtime', 'report_daemon', safe_str)
    }

    # 2. Initialize the nested dictionary
    config_data = {
        'smtp': {},
        'cmlapi': {},
        'ldap': {},
        'runtime': {}
    }

    with app.app_context():
        db_configs = Config.query.all()

        # 4. Populate the dictionary and apply the type cast
        for item in db_configs:
            if item.attr in schema_mapping:
                section, dict_key, cast_func = schema_mapping[item.attr]
                
                # Pass the raw database value through the assigned casting function
                config_data[section][dict_key] = cast_func(item.value)

        return config_data


def create_local_user(username, password, mail, fullname, is_admin, config_admin):
    with app.app_context():
        # Check if the user already exists to prevent duplicate errors
        existing_user = db.session.execute(db.select(User).filter_by(username=username)).scalar()
        
        if existing_user is not None:
            print(f"[-] Error: User '{username}' already exists in the database.")
            return

        # Hash the password for local authentication
        hashed_password = generate_password_hash(password)

        # Create the new user object
        new_user = User(
            username=username,
            password=hashed_password,
            mail=mail,
            fullname=fullname,
            is_external=False,        # Explicitly set to False
            is_admin=is_admin,    # Now a boolean value directly from argparse
            config_admin=config_admin
        )

        # Save to database
        db.session.add(new_user)
        db.session.commit()

        print(f"[+] Successfully created local user: {username}")
        print(f"    - Email: {mail}")
        print(f"    - Admin: {is_admin}")
        print(f"    - Config Admin: {config_admin}")
        print(f"    - External: False")


def update_user_details(username, password=None, mail=None, fullname=None, is_admin=None, config_admin=None):
    with app.app_context():
        # Check if the user already exists to prevent duplicate errors
        user = db.session.execute(db.select(User).filter_by(username=username)).scalar()

        if user is None:
            print(f"[-] Error: User '{username}' doesn't exist in the database.")
            return

        if user.is_external:
            if password is not None or mail is not None or fullname is not None:
                print(f"[-] Error: Can not update external User '{username}'.")
                return
        else:
            if password is not None:
                user.password = generate_password_hash(password)
            if mail is not None:
                user.mail = mail
            if fullname is not None:
                user.fullname = fullname

        if is_admin is not None:
                user.is_admin = is_admin

        if config_admin is not None:
            user.config_admin = config_admin
            
        # Commit the changes to the database
        try:
            db.session.commit()
            print(f"[+] Successfully updated details for '{username}'.")
        except Exception as e:
            db.session.rollback() # Rollback in case of an error (e.g., database constraint failure)
            print(f"[-] Database error while updating user '{username}': {e}")


def delete_user(username):
    with app.app_context():
        user = db.session.execute(db.select(User).filter_by(username=username)).scalar()

        if user is None:
            print(f"[-] Error: User '{username}' doesn't exist in the database.")
            return

        try:
            db.session.delete(user)
            db.session.commit()
            print(f"[+] Successfully deleted user '{username}'.")
        except Exception as e:
            db.session.rollback() # Rollback in case of an error (e.g., a foreign key constraint issue)
            print(f"[-] Database error while deleting user '{username}': {e}")


def export_users_to_csv(filename):
    with app.app_context():
        try:
            df = pd.read_sql(db.select(User), con=db.engine)

            # Check if the DataFrame is empty (no users found)
            if df.empty:
                print("[-] No users found in the database. Export cancelled.")
                return

            df.to_csv(filename, index=False, encoding='utf-8')        
            print(f"[+] Successfully exported {len(df)} users to '{filename}'.")
        except Exception as e:
            print(f"[-] Error during pandas export: {e}")


def main():
    parser = argparse.ArgumentParser(
        prog="CML Monitor DB Utils",
        description="Manage CML Monitor Database"
    )
    subparsers = parser.add_subparsers(title="commands", dest="command", required=True)

    # --- CONFIGS SUBPARSERS ---
    config_parser = subparsers.add_parser('config', help="Manage configs table")
    config_subparsers = config_parser.add_subparsers(title="config_commands", dest="config_command", required=True)

    # --- CONFIG INIT PARSER ---
    config_init_parser = config_subparsers.add_parser("init", help="Initialize Configs table")
    config_init_parser.add_argument('-u', '--username', required=True, help="Username who performed initialization")

    # --- CONFIG EXPORT PARSER ---
    config_export_parser = config_subparsers.add_parser("export", help="Export Configs table to a csv file")
    config_export_parser.add_argument('-f', '--filename', default="configs.csv", help="exported csv file path")

    # --- USER SUBPARSERS ---
    user_parser = subparsers.add_parser('user', help="Manage users table.")
    user_subparsers = user_parser.add_subparsers(title="user_commands", dest="user_command", required=True)

    # --- USER CREATE PARSER ---
    user_create_parser = user_subparsers.add_parser('create', help="Create a local user in the database.")
    user_create_parser.add_argument('-u', '--username', required=True, help="Username for the new user")
    user_create_parser.add_argument('-p', '--password', required=True, help="Password for the new user")
    user_create_parser.add_argument('-m', '--mail', required=True, help="Email address")
    user_create_parser.add_argument('-f', '--fullname', required=True, help="Full name of the user")
    user_create_parser.add_argument('--is-admin', action='store_true', help="Set this flag to make the user an admin")
    user_create_parser.add_argument('--config-admin', action='store_true', help="Set this flag to make the user a config admin")

    # --- USER UPDATE PARSER ---
    user_update_parser = user_subparsers.add_parser('update', help="Update an existing user in the database.")
    user_update_parser.add_argument('-u', '--username', required=True, help="Username of the user to update")
    user_update_parser.add_argument('-p', '--password', default=None, help="Password for the user")
    user_update_parser.add_argument('-m', '--mail', default=None, help="Email address")
    user_update_parser.add_argument('-f', '--fullname', default=None, help="Full name of the user")
    user_update_parser.add_argument('--is-admin', action=argparse.BooleanOptionalAction, default=None, help="Set to --is-admin to grant admin, --no-is-admin to revoke")
    user_update_parser.add_argument('--config-admin', action=argparse.BooleanOptionalAction, default=None, help="Set to --config-admin to grant config admin, --no-config-admin to revoke")

    # --- USER DELETE PARSER ---
    user_delete_parser = user_subparsers.add_parser('delete', help="Delete an existing user in the database.")
    user_delete_parser.add_argument('-u', '--username', required=True, help="Username of the user to delete")

    # --- USER EXPORT PARSER ---
    user_export_parser = user_subparsers.add_parser('export', help="Export Users table to a csv file")
    user_export_parser.add_argument('-f', '--filename', default="users.csv", help="exported csv file path")

    args = parser.parse_args()

    # --- COMMAND ROUTING ---
    if args.command == 'config':
        if args.config_command == 'init':
            print(f"Initializing configs table with Username: {args.username}...")
            init_configs(args.username)
        elif args.config_command == 'export':
            print(f"Exporting Users table to '{args.filename}'...")
            export_configs_to_csv(args.filename)
    elif args.command == 'user':
        if args.user_command == 'create':
            print(f"Creating user '{args.username}' (Admin: {args.is_admin}) (Config Admin: {args.config_admin})...")
            create_local_user(args.username, args.password, args.mail, args.fullname, args.is_admin, args.config_admin)
        elif args.user_command == 'update':
            print(f"Updating user '{args.username}'...")
            update_user_details(args.username, args.password, args.mail, args.fullname, args.is_admin, args.config_admin)
        elif args.user_command == 'delete':
            print(f"Deleting user '{args.username}'...")
            delete_user(args.username)
        elif args.user_command == 'export':
            print(f"Exporting Users table to '{args.filename}'...")
            export_users_to_csv(args.filename)


if __name__ == '__main__':
    main()
