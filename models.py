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
