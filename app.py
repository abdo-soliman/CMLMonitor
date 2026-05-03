import os

os.chdir(os.environ["WORK_DIR"])

import io
import ast
import json
import tempfile
import threading
import pandas as pd
import process_manager
from extensions import db
from sqlalchemy import event
from models import User, Config
from pydantic import ValidationError
from cmlmonitor_db import init_configs
from smtp_utils import smtp_test_email
from workload_manager import WorkloadManager
from werkzeug.security import check_password_hash, generate_password_hash
from schemas import AdminSchema, SetupSchema, LDAPSchema, CMLSchema, AlertsSchema
from cmlmonitor import check_cml_connection, is_cml_apikey_admin, test_kube_config
from ldap_utils import is_ldap_enabled, authenticate_and_user_data, validate_ldap_search
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from utils import WorkloadType, SearchFilters, OrderByFilters, pagination_to_indecies, is_none_or_empty
from flask import Flask, flash, render_template, request, redirect, url_for, jsonify, send_file, current_app


app = Flask(__name__)
app.secret_key = 'super_secret_key'  # Change this in production


# --- Database Configuration ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cmlmonitor.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# --- Flask-Login Initialization ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
workload_manager = None


def init_workload_manager():
    """Helper function to instantiate and start the global workload manager."""
    global workload_manager
    if workload_manager is None:
        # Import here if needed to avoid circular imports, or assume it's imported at the top
        workload_manager = WorkloadManager(60)
        workload_manager.start_caching()
        print("Workload Manager initialized and caching started.")


def is_cml_configed():
    with app.app_context():
        cml_configs = Config.query.filter(Config.attr.like('cml.%')).all()
        configs = {config.attr: config.value for config in cml_configs}

        return not (is_none_or_empty(configs['cml.workspace_domain']) or is_none_or_empty(configs['cml.api_key']) or is_none_or_empty(configs['cml.namespace_prefix']))


# Create tables and initialize workload/alert processes before running
with app.app_context():
    db.create_all()
    try:
        init_config = Config.query.filter_by(attr='init').first()
        # 2. If setup is already complete, start the manager immediately
        if init_config and init_config.value == '1':
            init_workload_manager()
    except Exception as e:
        # The database might not be created/migrated yet
        print(f"Skipping WorkloadManager initialization: {e}")

    try:
        enabled_conf = Config.query.filter_by(attr='alert.enabled').first()
        if enabled_conf and enabled_conf.value == '1':
            print("Alerts enabled in DB. Syncing background processes...")

            alert_cron_conf = Config.query.filter_by(attr='alert.runtime.alert_cron').first()
            report_cron_conf = Config.query.filter_by(attr='alert.runtime.report_cron').first()

            if alert_cron_conf and alert_cron_conf.value.strip():
                process_manager.start_process('alert', '24h')

            if report_cron_conf and report_cron_conf.value.strip():
                process_manager.start_process('report', '1s')
    except Exception as e:
        print(f"Warning: Could not sync background processes on boot: {e}")


def sync_alert_processes(app):
    """
    Runs the synchronization logic inside an application context.
    We pass 'app' so the database queries work inside the new thread.
    """
    with app.app_context():
        try:
            enabled_conf = Config.query.filter_by(attr='alert.enabled').first()
            if enabled_conf and enabled_conf.value == '1':
                print("Alerts enabled in DB. Syncing background processes...")

                alert_cron_conf = Config.query.filter_by(attr='alert.runtime.alert_cron').first()
                report_cron_conf = Config.query.filter_by(attr='alert.runtime.report_cron').first()

                if alert_cron_conf and alert_cron_conf.value.strip():
                    process_manager.restart_process('alert', '24h')
                elif process_manager.get_status()["alert_running"]:
                    process_manager.stop_process("alert")

                if report_cron_conf and report_cron_conf.value.strip():
                    process_manager.restart_process('report', '1s')
                elif process_manager.get_status()["report_running"]:
                    process_manager.stop_process("report")
            else:
                process_manager.stop_all()

        except Exception as e:
            print(f"Warning: Could not sync background processes: {e}")


# trigger alert process sync on config table changes
@event.listens_for(Config, 'after_update')
def receive_config_update(mapper, connection, target):
    # We only care if one of these specific attributes was updated
    relevant_attrs = [
        'alert.enabled', 
        'alert.runtime.alert_cron', 
        'alert.runtime.report_cron'
    ]

    if target.attr in relevant_attrs:
        # Check SQLAlchemy's history to ensure the 'value' column actually changed
        state = db.inspect(target)
        if state.attrs.value.history.has_changes():
            print(f"Config '{target.attr}' updated. Triggering process sync...")
            
            # Spin off a thread so process_manager doesn't block the DB commit
            # We use _get_current_object() to safely pass the app to the thread
            app = current_app._get_current_object()
            thread = threading.Thread(target=sync_alert_processes, args=(app,))
            thread.start()


@login_manager.user_loader
def load_user(user_id):
    """Reloads the user object from the session ID."""
    return db.session.get(User, int(user_id))


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.before_request
def enforce_access_policies():
    """Runs before every request to enforce global security and state policies."""
    
    # Allow safe routing during the absolute initial setup phase
    allowed_admin_setup = ['setup_admin_page', 'create_admin', 'static']
    
    try:
        # 1. DAY 0 CHECK: If no users and no configs exist, force Admin Creation
        if User.query.first() is None and Config.query.first() is None:
            if request.endpoint not in allowed_admin_setup:
                return redirect(url_for('setup_admin_page'))
            return # Allow them to proceed to the admin creation page
    except Exception:
        # Silently pass if the database tables aren't fully initialized yet 
        pass

    if current_user.is_authenticated:
        if current_user.is_external:
            try:
                if not is_ldap_enabled():
                    logout_user()
                    flash("LDAP Authentication is Disabled at the moment", "warning")
                    return redirect(url_for('login'))
            except Exception:
                logout_user()
                return redirect(url_for('login'))

        # 2. CONFIGURATION PHASE CHECK
        allowed_endpoints = ['setup_wizard', 'test_setup_cml_connection', 'test_ldap_connection', 'test_smtp_connection', 'save_setup', 'login', 'logout', 'static']

        if request.endpoint not in allowed_endpoints:
            try:
                init_config = Config.query.filter_by(attr='init').first()
                if init_config and init_config.value == '0':
                    if current_user.config_admin:
                        return redirect(url_for('setup_wizard'))
                    else:
                        logout_user()
                        flash("System is awaiting initial setup.", "warning")
                        return redirect(url_for('login'))
            except Exception:
                pass


# --- Routes ---
@app.route('/setup-admin', methods=['GET'])
def setup_admin_page():
    # Double-check security: if data exists, boot them to login
    if User.query.first() is not None or Config.query.first() is not None:
        return redirect(url_for('login'))
    return render_template('setup_admin.html')


@app.route('/api/setup/admin', methods=['POST'])
def create_admin():
    # Security lock
    if User.query.first() is not None or Config.query.first() is not None:
        return jsonify({"success": False, "message": "Initialization already completed."}), 403

    raw_data = request.json or {}

    # 1. Validate data using Pydantic
    try:
        valid_data = AdminSchema(**raw_data)
    except ValidationError as e:
        error_msg = e.errors()[0]['msg']
        error_field = e.errors()[0]['loc'][0]
        return jsonify({
            "success": False, 
            "message": f"Validation Error on '{error_field}': {error_msg}"
        }), 400

    try:
        # 2. Create the Admin User
        # Map the validated Pydantic fields to your database model's fields
        hashed_pw = generate_password_hash(valid_data.password)
        new_user = User(
            username=valid_data.username,
            password=hashed_pw,
            fullname=valid_data.full_name,  # Maps to 'fullname' in DB
            mail=valid_data.email,          # Maps to 'mail' in DB
            is_admin=True,
            config_admin=True,
            is_external=False
        )
        db.session.add(new_user)
        db.session.commit() # Must commit here so init_configs can find the user

        # 3. Run your init_configs function
        init_configs(valid_data.username)

        # 4. Validation: Check if configs actually seeded
        if Config.query.first() is None:
            raise Exception("Configurations failed to initialize. Please check the backend logs.")

        return jsonify({"success": True, "message": "Admin user and configurations initialized."})

    except Exception as e:
        # 5. ROLLBACK: If anything fails, wipe the tables to restore the 'Day 0' state
        db.session.rollback()
        try:
            db.session.query(Config).delete()
            db.session.query(User).delete()
            db.session.commit()
        except Exception as rollback_err:
            print(f"Critical Rollback Error: {rollback_err}")

        return jsonify({"success": False, "message": f"Initialization failed: {str(e)}"}), 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # 1. Check if the user exists in the local database
        user = db.session.execute(db.select(User).filter_by(username=username)).scalar()

        if user:

            # 2. User exists: Check if they are internal or external
            if not user.is_external:
                # LOCAL AUTHENTICATION
                if user.password and check_password_hash(user.password, password):
                    login_user(user)
                    return redirect(url_for('home'))
                else:
                    return render_template('login.html', error="Invalid credentials")
            else:
                if is_ldap_enabled():
                    # EXTERNAL (LDAP) AUTHENTICATION for existing DB user
                    user_data = authenticate_and_user_data(username, password)
                    if user_data:
                        login_user(user)
                        return redirect(url_for('home'))
                    else:
                        return render_template('login.html', error="Invalid credentials")
                else:
                    return render_template('login.html', error="Invalid credentials")
        else:
            # 3. User does NOT exist in DB: Attempt LDAP Authentication
            user_data = authenticate_and_user_data(username, password)

            if user_data is not None:
                # LDAP Success! Auto-provision the user in the SQLite database
                new_user = User(
                    username=username,
                    password=None,               # Set to NULL
                    mail=user_data.get('mail'),
                    fullname=user_data.get('displayName'),
                    is_external=True,            # Mark as LDAP user
                    is_admin=False,              # Always false by default
                    config_admin=False
                )

                db.session.add(new_user)
                db.session.commit()

                # Log the newly created user in
                login_user(new_user)
                return redirect(url_for('home'))
            else:
                # LDAP Failed and User not in DB
                return render_template('login.html', error="Invalid credentials")

    # Simple HTML form for GET request
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/setup', methods=['GET'])
@login_required
def setup_wizard():
    # 1. Security Check: Must be config_admin
    if not current_user.config_admin:
        flash("You do not have permission to perform initial setup.", "error")
        return redirect(url_for('home'))

    # 2. State Check: Only allow if init == '0'
    init_config = Config.query.filter_by(attr='init').first()
    if init_config and init_config.value == '1':
        return redirect(url_for('home'))

    return render_template('setup.html', user=current_user)


@app.route('/api/setup/test-cml', methods=['POST'])
@login_required
def test_setup_cml_connection():
    """Endpoint to test CML credentials before allowing the user to proceed."""
    if not current_user.config_admin:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.json

    # Use the keys that match the JS setupData payload
    domain = data.get('cml_workspace_domain')
    api_key = data.get('cml_api_key')
    kube_content = data.get('cml_kubeconfig_content')

    if not kube_content:
        return jsonify({"success": False, "message": "Kubeconfig file content is missing."})

    # Test CML Connection
    connected, message = check_cml_connection(domain, api_key)
    if connected:
        # Test that the API Key is for an admin user.
        if is_cml_apikey_admin(domain, api_key):
            tmp_path = None
            try:
                # Create a temporary file in /tmp to write rke3.yaml to it for testing
                with tempfile.NamedTemporaryFile(mode='w', delete=False, dir='/tmp', suffix='.yaml') as tmp_file:
                    tmp_file.write(kube_content)
                    tmp_path = tmp_file.name

                # Test the kubenetes connection using the uploaded yaml file
                kube_connected, kube_message = test_kube_config(tmp_path)

                if kube_connected:
                    return jsonify({"success": True, "message": "CML and Kubernetes were configured successfully!"})

                return jsonify({"success": False, "message": f"CML verified, but K8s failed: {kube_message}"})
            except Exception as e:
                return jsonify({"success": False, "message": f"Error handling kubeconfig: {str(e)}"})
            finally:
                # Delete the temporary file
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
        else:
            return jsonify({"success": False, "message": "Provided API Key is not for an admin user."})
    else:
        return jsonify({"success": False, "message": message})


@app.route('/api/config/test-cml', methods=['POST'])
@login_required
def test_config_cml_connection():
    """Endpoint to test CML credentials before allowing the user to proceed."""
    if not current_user.config_admin:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.json

    # Use the keys that match the JS setupData payload
    domain = data.get('cml_workspace_domain')
    api_key = data.get('cml_api_key')
    kube_content = data.get('cml_kubeconfig_content')

    # Test CML Connection
    connected, message = check_cml_connection(domain, api_key)
    if connected:
        # Test that the API Key is for an admin user.
        if is_cml_apikey_admin(domain, api_key):
            if not kube_content:
                # SKIP K8s TEST
                return jsonify({"success": True, "message": "CML configured successfully (Kubernetes test skipped as no new file was provided)."})
            else:
                tmp_path = None
                try:
                    # Create a temporary file in /tmp to write rke3.yaml to it for testing
                    with tempfile.NamedTemporaryFile(mode='w', delete=False, dir='/tmp', suffix='.yaml') as tmp_file:
                        tmp_file.write(kube_content)
                        tmp_path = tmp_file.name

                    # Test the kubenetes connection using the uploaded yaml file
                    kube_connected, kube_message = test_kube_config(tmp_path)

                    if kube_connected:
                        return jsonify({"success": True, "message": "CML and Kubernetes were configured successfully!"})

                    return jsonify({"success": False, "message": f"CML verified, but K8s failed: {kube_message}"})
                except Exception as e:
                    return jsonify({"success": False, "message": f"Error handling kubeconfig: {str(e)}"})
                finally:
                    # Delete the temporary file
                    if tmp_path and os.path.exists(tmp_path):
                        os.remove(tmp_path)
        else:
            return jsonify({"success": False, "message": "Provided API Key is not for an admin user."})
    else:
        return jsonify({"success": False, "message": message})


@app.route('/api/test-ldap', methods=['POST'])
@login_required
def test_ldap_connection():
    if not current_user.config_admin:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.json
    server_url = data.get('ldap_server')
    port = int(data.get('ldap_port', 389))
    base_dn = data.get('ldap_base_dn')
    bind_dn = data.get('ldap_bind_dn')
    bind_password = data.get('ldap_bind_password')
    test_user = data.get('test_username')

    try:
        db_password_config = Config.query.filter_by(attr='ldap.bind_password').first()
        db_has_password = db_password_config and bool(db_password_config.value.strip())
        if not bind_password and not db_has_password:
            # DB has no password, and user didn't provide one
            return jsonify({"success": False, "message": "Bind User Password is required because no password is currently saved."})        
    
        if not bind_password:
            bind_password = db_password_config.value.strip()
    
        # Basic validation
        if not all([server_url, base_dn, bind_dn, bind_password, test_user]):
            return jsonify({"success": False, "message": "All fields, including Test Username, are required to verify the connection."})
    
        result, message = validate_ldap_search(server_url, port, base_dn, bind_dn, bind_password, test_user)
        return jsonify({"success": result, "message": message})
    except Exception as e:
        return jsonify({ "sucess": False, "message": str(e) })


@app.route('/api/test-smtp', methods=['POST'])
@login_required
def test_smtp_connection():
    if not current_user.config_admin:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.json
    server = data.get('smtp_server')
    port = int(data.get('smtp_port', 587))
    use_tls = data.get('smtp_use_tls') == '1'
    user = data.get('smtp_user')
    password = data.get('smtp_password')
    sender = data.get('smtp_sender_email')
    recipients = data.get('recipients')

    if not server or not sender:
        return jsonify({"success": False, "message": "Server URL and Sender Email are required."})

    db_password_config = Config.query.filter_by(attr='alert.smtp.password').first()
    db_has_password = db_password_config and bool(db_password_config.value.strip())

    if not password and not db_has_password:
        # DB has no password, and user didn't provide one
        return jsonify({"success": False, "message": "SMTP User Password is required because no password is currently saved."})        

    if not password:
        password = db_password_config.value.strip()
    
    result, message = smtp_test_email(server, port, use_tls, user, password, sender, recipients)

    if result:
        return jsonify({"success": True, "message": "SMTP connection successful!"})

    return jsonify({"success": False, "message": message})


@app.route('/api/setup/save', methods=['POST'])
@login_required
def save_setup():
    """Saves the wizard configs and locks the setup by setting init=1."""
    if not current_user.config_admin:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    init_config = Config.query.filter_by(attr='init').first()
    if init_config and init_config.value == '1':
         return jsonify({"success": False, "message": "Setup already completed."}), 400

    # Map the abstract frontend/schema keys to the actual database attributes
    SCHEMA_TO_DB_MAP = {
        'cml_workspace_domain': 'cml.workspace_domain',
        'cml_api_key': 'cml.api_key',
        'cml_namespace_prefix': 'cml.namespace_prefix',
        'ldap_enabled': 'ldap.enabled',
        'ldap_server': 'ldap.server',
        'ldap_port': 'ldap.port',
        'ldap_base_dn': 'ldap.base_dn',
        'ldap_bind_dn': 'ldap.bind_dn',
        'ldap_bind_password': 'ldap.bind_password',
        'alert_enabled': 'alert.enabled',
        'use_tls': 'alert.smtp.use_tls',
        'smtp_server': 'alert.smtp.server',
        'smtp_port': 'alert.smtp.port',
        'smtp_user': 'alert.smtp.user',
        'smtp_password': 'alert.smtp.password',
        'sender_email': 'alert.smtp.sender_email'
    }

    raw_data = request.json or {}

    # 1. Validate data using Pydantic
    try:
        validated_data = SetupSchema(**raw_data)
    except ValidationError as e:
        # Extract the first error message for a cleaner frontend alert
        error_msg = e.errors()[0]['msg']
        error_field = e.errors()[0]['loc'][0]
        return jsonify({
            "success": False, 
            "message": f"Validation Error on '{error_field}': {error_msg}"
        }), 400

    # --- Save the rke2.yaml file ---
    secure_dir = os.path.join(current_app.root_path, 'secure_configs')
    os.makedirs(secure_dir, exist_ok=True)
    kubeconfig_path = os.path.join(secure_dir, 'rke2.yaml')

    try:
        with open(kubeconfig_path, 'w', encoding='utf-8') as f:
            f.write(validated_data.cml_kubeconfig_content)
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed to save kubeconfig file to disk: {str(e)}"}), 500

    # Iterate through the mapping and update the database
    for schema_key, db_attr in SCHEMA_TO_DB_MAP.items():
        value = getattr(validated_data, schema_key)

        # Convert values to strings for the database (e.g., True -> '1', False -> '0', None -> '')
        if isinstance(value, bool):
            str_value = '1' if value else '0'
        elif value is None:
            str_value = ''
        else:
            str_value = str(value)

        config_item = Config.query.filter_by(attr=db_attr).first()
        if config_item:
            config_item.value = str_value
            config_item.updated_by = current_user.username

    # Manually update the file path record
    kube_path_config = Config.query.filter_by(attr='cml.kubeconfig_path').first()
    if kube_path_config:
        kube_path_config.value = kubeconfig_path
        kube_path_config.updated_by = current_user.username

    # Lock the initial setup
    if init_config:
        init_config.value = '1'
        init_config.updated_by = current_user.username

    # Commit to the database
    try:
        db.session.commit()
        init_workload_manager()
        return jsonify({"success": True, "message": "Setup completed successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Database error: {str(e)}"}), 500


@app.route('/')
@login_required
def home():
    if not current_user or current_user.is_anonymous:
        return redirect(url_for('login'))

    workloads, counts, _ = workload_manager.get(current_user)

    start_index, end_index, _, _, max_number_of_pages = pagination_to_indecies(25, 1, len(workloads))
    search_data = workload_manager.get_search_data()
    search_data_json = json.dumps(search_data, default=list)

    user = {
        "username": current_user.username,
        "fullname": current_user.fullname,
        "mail": current_user.mail,
        "config_admin": current_user.config_admin
    }
    # Render the initial page with current data
    return render_template('home.html', \
                        user=user, \
                        cml_configured=is_cml_configed(), \
                        workloads=workloads[start_index:end_index], \
                        search_data=search_data_json, \
                        usernames=search_data[SearchFilters.USERNAME.value], \
                        num_sessions=counts[WorkloadType.SESSION.value], \
                        num_applications=counts[WorkloadType.APPLICATION.value], \
                        num_jobs=counts[WorkloadType.JOB.value], \
                        total_number_of_workload=counts[WorkloadType.ALL.value], \
                        max_pages=max_number_of_pages)


@app.route('/config')
@login_required
def config():
    if not current_user or current_user.is_anonymous:
        return redirect(url_for('login'))

    if not current_user.config_admin:
        return jsonify({"error": "Unauthorized"}), 401

    user = {
        "username": current_user.username,
        "fullname": current_user.fullname,
        "mail": current_user.mail,
        "config_admin": current_user.config_admin
    }

    all_configs = Config.query.all()

    # Map the 'attr' column to the 'value' column using dictionary comprehension
    configs = {config.attr: config.value for config in all_configs}
    configs.pop('ldap.bind_password', None)
    configs.pop('alert.smtp.password', None)

    # cast string to string array
    alert_recipient_emails = ast.literal_eval(configs["alert.smtp.alert_recipient_emails"])
    report_recipient_emails = ast.literal_eval(configs["alert.smtp.report_recipient_emails"])

    configs["alert_emails"] = ",".join(alert_recipient_emails)
    configs["report_emails"] = ",".join(report_recipient_emails)

    # Grab the active tab from the URL, default to 'ldap'
    active_tab = request.args.get('active_tab', 'ldap')

    # Render the initial page with current data
    return render_template('config.html', \
                        user=user,
                        configs=configs,
                        active_tab=active_tab)


@app.route('/config/ldap', methods=['POST'])
@login_required
def update_ldap():
    if not current_user or current_user.is_anonymous:
        return redirect(url_for('login'))
    
    if not current_user.config_admin:
        return jsonify({"error": "Unauthorized"}), 401

    raw_data = {
        'ldap_enabled': request.form.get('ldap_enabled', '0'),
        'server': request.form.get('server', ''),
        'port': request.form.get('port') or None,
        'base_dn': request.form.get('base_dn', ''),
        'bind_dn': request.form.get('bind_dn', ''),
        'bind_password': request.form.get('bind_password', '')
    }

    try:
        valid_data = LDAPSchema(**raw_data)
    except ValidationError as e:
        for error in e.errors():
            field_name = error['loc'][0]
            error_msg = error['msg']
            flash(f"Error in {field_name}: {error_msg}", "error")
        return redirect(url_for('config', active_tab="ldap"))

    valid_ldap_configs = {
        'ldap.enabled': '1' if valid_data.ldap_enabled else '0',
        'ldap.server': valid_data.server,
        'ldap.port': str(valid_data.port) if valid_data.port else '',
        'ldap.base_dn': valid_data.base_dn,
        'ldap.bind_dn': valid_data.bind_dn
    }

    new_password = valid_data.bind_password
    db_password_config = Config.query.filter_by(attr='ldap.bind_password').first()
    db_has_password = db_password_config and bool(db_password_config.value.strip())

    if not new_password and not db_has_password:
        # DB has no password, and user didn't provide one
        flash("Bind User Password is required because no password is currently saved.", "error")
        return redirect(url_for('config', active_tab="ldap"))

    # If a new password was provided, add it to our update dictionary
    if new_password:
        valid_ldap_configs['ldap.bind_password'] = new_password

    for attr, new_value in valid_ldap_configs.items():
        config_item = Config.query.filter_by(attr=attr).first()

        if config_item:
            config_item.value = new_value
            config_item.updated_by = current_user.username
        else:
            # Fallback in case the config attribute was accidentally deleted from the DB
            new_config = Config(attr=attr, value=new_value, updated_by=current_user.username)
            db.session.add(new_config)

    try:
        db.session.commit()
        flash("LDAP settings updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred while saving: {str(e)}", "error")

    return redirect(url_for('config', active_tab="ldap"))


@app.route('/config/cml', methods=['POST'])
@login_required
def update_cml():
    if not current_user or current_user.is_anonymous:
        return redirect(url_for('login'))

    if not current_user.config_admin:
        return jsonify({"error": "Unauthorized"}), 401

    raw_data = {
        'workspace_domain': request.form.get('workspace_domain', ''),
        'api_key': request.form.get('api_key', ''),
        'namespace_prefix': request.form.get('namespace_prefix', '')
    }

    # Intercept the uploaded file (if provided)
    kube_file = request.files.get('kubeconfig_file')
    if kube_file and kube_file.filename:
        try:
            # Decode bytes to text so Pydantic and Python can process it cleanly
            raw_data['kubeconfig_content'] = kube_file.read().decode('utf-8')
        except UnicodeDecodeError:
            flash("Invalid file encoding. Please upload a valid YAML text file.", "error")
            return redirect(url_for('config', active_tab="cml"))

    try:
        valid_data = CMLSchema(**raw_data)
    except ValidationError as e:
        for error in e.errors():
            field_name = error['loc'][0]
            error_msg = error['msg']
            flash(f"Error in {field_name}: {error_msg}", "error")
        return redirect(url_for('config', active_tab="cml"))

    valid_cml_configs = {
        'cml.workspace_domain': valid_data.workspace_domain,
        'cml.api_key': valid_data.api_key,
        'cml.namespace_prefix': valid_data.namespace_prefix
    }

    # Update standard CML configs
    for attr, new_value in valid_cml_configs.items():
        config_item = Config.query.filter_by(attr=attr).first()

        if config_item:
            config_item.value = new_value
            config_item.updated_by = current_user.username
        else:
            new_config = Config(attr=attr, value=new_value, updated_by=current_user.username)
            db.session.add(new_config)

    # If a new kubeconfig file was uploaded, save it to disk and update its DB path
    if valid_data.kubeconfig_content:
        secure_dir = os.path.join(current_app.root_path, 'secure_configs')
        os.makedirs(secure_dir, exist_ok=True)
        kubeconfig_path = os.path.join(secure_dir, 'rke2.yaml')

        try:
            with open(kubeconfig_path, 'w', encoding='utf-8') as f:
                f.write(valid_data.kubeconfig_content)
            # Update the path in the database
            kube_path_config = Config.query.filter_by(attr='cml.kubeconfig_path').first()
            if kube_path_config:
                kube_path_config.value = kubeconfig_path
                kube_path_config.updated_by = current_user.username
            else:
                new_kube_config = Config(attr='cml.kubeconfig_path', value=kubeconfig_path, updated_by=current_user.username)
                db.session.add(new_kube_config)
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to save kubeconfig file to disk: {str(e)}", "error")
            return redirect(url_for('config', active_tab="cml"))

    try:
        db.session.commit()
        flash("CML settings updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred while saving: {str(e)}", "error")

    return redirect(url_for('config', active_tab="cml"))


@app.route('/config/alert', methods=['POST'])
@login_required
def update_alerts():
    if not current_user or current_user.is_anonymous:
        return redirect(url_for('login'))

    if not current_user.config_admin:
        return jsonify({"error": "Unauthorized"}), 401

    raw_data = {
        'alert_enabled': request.form.get('alert_enabled', '0'),
        'use_tls': request.form.get('use_tls', '0'),
        'smtp_server': request.form.get('smtp_server', ''),
        'smtp_port': request.form.get('smtp_port') or None, 
        'smtp_user': request.form.get('smtp_user', ''),
        'smtp_password': request.form.get('smtp_password', ''),
        'alert_subject': request.form.get('alert_subject', ''),
        'report_subject': request.form.get('report_subject', ''),
        'sender_email': request.form.get('sender_email') or None,
        'alert_recipient_emails': request.form.get('alert_recipient_emails', ''),
        'report_recipient_emails': request.form.get('report_recipient_emails', ''),
        'alert_cron': request.form.get('alert_cron', ''),
        'report_cron': request.form.get('report_cron', '')
    }

    try:
        valid_data = AlertsSchema(**raw_data)
    except ValidationError as e:
        for error in e.errors():
            field_name = error['loc'][0]
            error_msg = error['msg']
            flash(f"Error in {field_name}: {error_msg}", "error")
        return redirect(url_for('config', active_tab="alerts"))

    valid_alert_configs = {
        'alert.enabled': '1' if valid_data.alert_enabled else '0',
        'alert.smtp.use_tls': '1' if valid_data.use_tls else '0',
        'alert.smtp.server': valid_data.smtp_server,
        'alert.smtp.port': str(valid_data.smtp_port) if valid_data.smtp_port else '',
        'alert.smtp.user': valid_data.smtp_user,
        'alert.smtp.alert_subject': valid_data.alert_subject,
        'alert.smtp.report_subject': valid_data.report_subject,
        'alert.smtp.sender_email': valid_data.sender_email or '',
        'alert.smtp.alert_recipient_emails': json.dumps(valid_data.alert_recipient_emails),
        'alert.smtp.report_recipient_emails': json.dumps(valid_data.report_recipient_emails),
        'alert.runtime.alert_cron': valid_data.alert_cron,
        'alert.runtime.report_cron': valid_data.report_cron
    }

    new_password = valid_data.smtp_password
    db_password_config = Config.query.filter_by(attr='alert.smtp.password').first()
    db_has_password = db_password_config and bool(db_password_config.value.strip())

    if not new_password and not db_has_password:
        # DB has no password, and user didn't provide one
        flash("SMTP User Password is required because no password is currently saved.", "error")
        return redirect(url_for('config', active_tab="alerts"))

    # If a new password was provided, add it to our update dictionary
    if new_password:
        valid_alert_configs['alert.smtp.password'] = new_password

    for attr, new_value in valid_alert_configs.items():
        config_item = Config.query.filter_by(attr=attr).first()
        if config_item:
            config_item.value = new_value
            config_item.updated_by = current_user.username
        else:
            new_config = Config(attr=attr, value=new_value, updated_by=current_user.username)
            db.session.add(new_config)

    try:
        db.session.commit()
        flash("Alerts settings updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred while saving: {str(e)}", "error")

    return redirect(url_for('config', active_tab="alerts"))


# --- API Endpoints (For AJAX) ---
@app.route('/api/refresh')
@login_required
def refresh_data():
    """Returns the current data as JSON. 
    We randomly update a value here to simulate live changes."""
    if not current_user or current_user.is_anonymous:
        return jsonify({"error": "Unauthorized"}), 401

    page_size = request.args.get('pageSize', default=25, type=int)
    page_number = request.args.get('pageNumber', default=1, type=int)
    filter = request.args.get('filter', default="all", type=str)
    search_filter = request.args.get('searchFilter', default="all", type=str)
    search_value = request.args.get('searchValue', default=None, type=str)
    order_by_filter = request.args.get('orderBy', default="all", type=str)

    raw_desc = request.args.get('desc', default='true').lower()
    if raw_desc not in ['true', 'false', '1', '0']:
        return jsonify({"error": "desc must be a boolean"}), 400
    order_by_desc = raw_desc in ['true', '1']
    
    try:
        new_filter = WorkloadType(filter)
        new_search_filter = SearchFilters(search_filter)
        new_order_by_filter = OrderByFilters(order_by_filter)

        workload_manager.refresh()
        workloads, counts, filters = workload_manager.get(current_user, new_filter, new_search_filter, search_value, order_by=new_order_by_filter, desc=order_by_desc)


        start_index, end_index, page_number, page_size, max_number_of_pages = pagination_to_indecies(page_size, page_number, len(workloads))
        search_data_json = json.dumps(workload_manager.get_search_data(), default=list)

        return jsonify({
            "page_number": page_number,
            "page_size": page_size,
            "max_pages": max_number_of_pages,
            "filter": filters["filter"],
            "search_filter": filters["search_filter"],
            "search_value": filters["search_value"],
            "search_data": search_data_json,
            "order_by_filter": filters["order_by_filter"],
            "desc": filters["desc"],
            "total_number_of_workload": counts[WorkloadType.ALL.value],
            "num_sessions": counts[WorkloadType.SESSION.value],
            "num_applications": counts[WorkloadType.APPLICATION.value],
            "num_jobs": counts[WorkloadType.JOB.value],
            "payload": workloads[start_index:end_index]
        })
    except ValueError:
        return jsonify({"error": "Invalid filter choice"}), 400


@app.route('/api/data')
def get_data():
    """Returns the current data as JSON. 
    We randomly update a value here to simulate live changes."""
    if not current_user or current_user.is_anonymous:
        return jsonify({"error": "Unauthorized"}), 401

    page_size = request.args.get('pageSize', default=25, type=int)
    page_number = request.args.get('pageNumber', default=1, type=int)
    filter = request.args.get('filter', default="all", type=str)
    search_filter = request.args.get('searchFilter', default="all", type=str)
    search_value = request.args.get('searchValue', default=None, type=str)
    order_by_filter = request.args.get('orderBy', default="all", type=str)

    raw_desc = request.args.get('desc', default='true').lower()
    if raw_desc not in ['true', 'false', '1', '0']:
        return jsonify({"error": "desc must be a boolean"}), 400
    order_by_desc = raw_desc in ['true', '1']

    try:
        new_filter = WorkloadType(filter)
        new_search_filter = SearchFilters(search_filter)
        new_order_by_filter = OrderByFilters(order_by_filter)

        workloads, counts, filters = workload_manager.get(current_user, new_filter, new_search_filter, search_value, order_by=new_order_by_filter, desc=order_by_desc)

        start_index, end_index, page_number, page_size, max_number_of_pages = pagination_to_indecies(page_size, page_number, len(workloads))
        search_data_json = json.dumps(workload_manager.get_search_data(), default=list)

        return jsonify({
            "page_number": page_number,
            "page_size": page_size,
            "max_pages": max_number_of_pages,
            "filter": filters["filter"],
            "search_filter": filters["search_filter"],
            "search_value": filters["search_value"],
            "search_data": search_data_json,
            "order_by_filter": filters["order_by_filter"],
            "desc": filters["desc"],
            "total_number_of_workload": counts[WorkloadType.ALL.value],
            "num_sessions": counts[WorkloadType.SESSION.value],
            "num_applications": counts[WorkloadType.APPLICATION.value],
            "num_jobs": counts[WorkloadType.JOB.value],
            "payload": workloads[start_index:end_index]
        })
    except ValueError:
        return jsonify({"error": "Invalid filter choice"}), 400


@app.route('/api/report')
def download_excel():
    workloads = workload_manager.expand_sub_workloads()
    df = pd.DataFrame(workloads)
    df = df.drop('show_full_name', axis=1)
    df = df.drop('age_seconds', axis=1)

    buffer = io.BytesIO()
    # Write the DataFrame to the buffer using the Excel writer using 'openpyxl' engine
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='CML Workload Report')

    # Reset the buffer's position to the beginning
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == '__main__':
    app.run(host="127.0.0.1", port=int(os.environ["CDSW_APP_PORT"]))
    # app.run(host="0.0.0.0", port=10000, debug=True)
