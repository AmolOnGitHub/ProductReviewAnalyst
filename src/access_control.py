from sqlalchemy.orm import Session
from src.models import UserCategoryAccess, Category


def set_user_categories(
    db: Session,
    user_id: int,
    category_ids: list[int],
) -> None:
    # Clear existing access
    db.query(UserCategoryAccess).filter(
        UserCategoryAccess.user_id == user_id
    ).delete()

    # Add new access
    for cid in category_ids:
        db.add(
            UserCategoryAccess(
                user_id=user_id,
                category_id=cid,
            )
        )

    db.commit()


def get_allowed_categories(
    db: Session,
    user_id: int,
) -> set[str]:
    rows = (
        db.query(Category.name)
        .join(UserCategoryAccess)
        .filter(UserCategoryAccess.user_id == user_id)
        .all()
    )
    return {r[0] for r in rows}