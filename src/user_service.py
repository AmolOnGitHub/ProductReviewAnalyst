from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models import User
from src.auth import hash_password, verify_password


def create_user(db: Session, email: str, password: str, role: str) -> User:
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("User already exists")
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = (
        db.query(User)
        .filter(User.email == email.lower().strip(), User.is_active.is_(True))
        .first()
    )
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user