from sqlalchemy.orm import Session
from typing import Optional

from app.database.models import User
from app.auth.security import get_password_hash, verify_password


"""Create a new user."""
def create_user(db: Session, email: str, username: str, password: str) -> User:
    hashed_password = get_password_hash(password)
    db_user = User(
        email=email,
        username=username,
        hashed_password=hashed_password
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user

"""Get a user by email."""
def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()

"""Get a user by username."""
def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()

"""Get a user by ID."""
def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()

"""Authenticate a user by email and password[when he tries to login in]."""
def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = get_user_by_email(db, email)

    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    return user
