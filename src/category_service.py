from sqlalchemy.orm import Session
from src.models import Category


def upsert_categories(db: Session, categories: set[str]) -> int:
    """
    Insert categories if they don't exist.
    Returns number of newly created categories.
    """
    existing = {
        c.name for c in db.query(Category).all()
    }

    new = categories - existing
    for name in new:
        db.add(Category(name=name))

    db.commit()
    return len(new)