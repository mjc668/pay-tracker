from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import current_user
from app.models.category import Category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.services import categories as categories_service
from app.services.categories import CategoryError

router = APIRouter(prefix="/categories", tags=["categories"])


def _raise_http(exc: CategoryError) -> NoReturn:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("", response_model=list[CategoryOut])
def list_categories(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    """List the user's categories (defaults first), seeding defaults if absent."""
    categories_service.ensure_default_categories(db, me)
    db.commit()
    return categories_service.list_categories(
        db, me.id, include_archived=include_archived
    )


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    try:
        category = categories_service.create_category(db, me.id, body.name)
    except CategoryError as exc:
        _raise_http(exc)
    db.commit()
    db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    """Rename and/or archive a category. Omitted fields are left unchanged."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        try:
            category = categories_service.get_for_user(
                db, me.id, category_id, allow_archived=True
            )
        except CategoryError as exc:
            _raise_http(exc)
        return category
    try:
        if "name" in updates and updates["name"] is not None:
            category = categories_service.rename_category(
                db, me.id, category_id, updates["name"]
            )
        else:
            category = categories_service.get_for_user(
                db, me.id, category_id, allow_archived=True
            )
        if "is_archived" in updates and updates["is_archived"] is not None:
            category = categories_service.set_archived(
                db, me.id, category_id, updates["is_archived"]
            )
    except CategoryError as exc:
        _raise_http(exc)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    """Delete an unused category. In-use categories must be archived instead."""
    try:
        categories_service.delete_category(db, me.id, category_id)
    except CategoryError as exc:
        _raise_http(exc)
    db.commit()
