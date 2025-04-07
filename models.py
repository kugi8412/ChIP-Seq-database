from sqlalchemy import MetaData
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

# Naming convention for easier migrations
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

db = SQLAlchemy(metadata=MetaData(naming_convention=naming_convention))


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<User {self.username}>"


class BedFile(db.Model):
    __tablename__ = 'bed_file'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False, unique=True)
    filepath = db.Column(db.String(300), nullable=False)
    total_length = db.Column(db.Integer, nullable=False, default=0)
    fingerprint = db.Column(db.Text, nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    user = db.relationship('User', backref=db.backref('bedfiles', lazy=True))

    def __repr__(self):
        return f"<BedFile {self.filename}>"
