from extensions import db
from flask_login import UserMixin

# ==========================================
# 1. SQLALCHEMY USER MODEL
# ==========================================
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=True) # Nullable for external users
    mail = db.Column(db.String(150), nullable=True)
    fullname = db.Column(db.String(150), nullable=True)
    is_external = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    config_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Timestamps using the database's current time
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now(), nullable=False)


class Config(db.Model):
    __tablename__ = 'configs'

    id = db.Column(db.Integer, primary_key=True)
    attr = db.Column(db.String(150), unique=True, nullable=False)
    value = db.Column(db.String(256), nullable=False) 

    # Foreign key linking to the User table's username column
    updated_by = db.Column(db.String(150), db.ForeignKey('users.username'), nullable=False)

    # Timestamps using the database's current time
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now(), nullable=False)

    user = db.relationship('User', backref='updated_configs')

    @classmethod
    def get_configs(cls, root):
        def safe_str(val, validate=False):
            return str(val) if val is not None else ""

        def safe_int(val):
            try:
                return int(val)
            except (ValueError, TypeError):
                return None  # Returns None if the port is blank or invalid

        def safe_bool(val):
            # Database stores '1' or '0', but this also catches 'true' just in case
            return str(val).strip().lower() in ['1', 'true', 'yes']

        def validate_none_or_empty(variable):
            if variable is None:
                raise ValueError("All Config variables must be avialable with correct vaules")

            if variable == "":
                raise ValueError("All Config variables must be avialable with correct vaules")

            return variable

        # 1. Define the mapping: DB Attribute -> (Section, Dictionary Key, Cast Function)
        schema_mapping = {
            # SMTP
            'alert.enabled': ('alert', 'alert_enabled', safe_bool),
            'alert.smtp.use_tls': ('alert', 'smtp_use_tls', safe_bool), # Cast to bool
            'alert.smtp.server': ('alert', 'smtp_server', safe_str),
            'alert.smtp.port': ('alert', 'smtp_port', safe_int),        # Cast to int
            'alert.smtp.user': ('alert', 'smtp_user', safe_str),
            'alert.smtp.password': ('alert', 'smtp_password', safe_str),
            'alert.smtp.alert_subject': ('alert', 'smtp_alert_subject', safe_str),
            'alert.smtp.report_subject': ('alert', 'smtp_report_subject', safe_str),
            'alert.smtp.sender_email': ('alert', 'sender_email', safe_str),
            'alert.smtp.alert_recipient_emails': ('alert', 'alert_recipient_emails', safe_str),
            'alert.smtp.report_recipient_emails': ('alert', 'report_recipient_emails', safe_str),

            # CML API
            'cml.workspace_domain': ('cml', 'WORKSPACE_DOMAIN', safe_str),
            'cml.api_key': ('cml', 'API_KEY', safe_str),
            'cml.namespace_prefix': ('cml', 'NAMESPACE_PREFIX', safe_str),
            'cml.kubeconfig_path': ('cml', 'KUBECONFIG_PATH', safe_str),
            'cml.ecs_webui_base_url': ('cml', 'ECS_WEBUI_BASE_URL', safe_str),

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
        config_data = {}

        db_configs = cls.query.all()
        validate_all = False
        match root:
            case "ldap":
                validate_all = safe_bool(next((config for config in db_configs if config.attr == "ldap.enabled"), None))
            case "alert":
                validate_all = safe_bool(next((config for config in db_configs if config.attr == "alert.enabled"), None))
            case "cml":
                validate_all = True
            case _:
                validate_all = False

        for item in db_configs:
            mapping = schema_mapping.get(item.attr)
            if mapping and root == mapping[0]:
                dict_key = mapping[1]
                cast_func = mapping[2]

                config_data[dict_key] = cast_func(item.value)
                if root == "cml" and dict_key == "ECS_WEBUI_BASE_URL":
                    continue

                config_data[dict_key] = validate_none_or_empty(config_data[dict_key]) if validate_all else config_data[dict_key]

        return config_data


class Runtime(db.Model):
    __tablename__ = 'runtimes'

    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(500), nullable=False)
    editor_name = db.Column(db.String(100), nullable=False)
    editor_version = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='ENABLED', nullable=False)

    # Foreign key linking to the User table's username column
    added_by = db.Column(db.String(150), db.ForeignKey('users.username'), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now(), nullable=False)

    # Enforce strictly ENABLED or DISABLED statuses at the database level
    __table_args__ = (
        db.CheckConstraint("status IN ('ENABLED', 'DISABLED')", name='check_valid_status'),
    )

    # Relationship to user
    user = db.relationship('User', backref='added_runtimes')
