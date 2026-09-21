"""Per-user bill categories.

Categories replace the old fixed `BillCategory` enum. Each user owns a set of
nine default rows (identified by `key`, translated in the UI) plus any number
of custom rows (`name` only). Bills reference `category_id`; renaming a
category relabels existing bills, and categories are archived rather than
deleted while any template still references them.

Nothing here commits — callers own the transaction. `ensure_default_categories`
flushes only; routers commit after calling it.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bill import BillTemplate
from app.models.category import Category
from app.models.user import User

DEFAULT_CATEGORY_KEYS: tuple[str, ...] = (
    "housing",
    "utilities",
    "insurance",
    "subscriptions",
    "entertainment",
    "transport",
    "healthcare",
    "education",
    "other",
)

# Backend copy of the frontend `Categories.*` messages for the nine defaults.
# Keep in sync with frontend/messages/{en,pl,de}.json.
_CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "housing": "Housing",
        "utilities": "Utilities",
        "insurance": "Insurance",
        "subscriptions": "Subscriptions",
        "entertainment": "Entertainment",
        "transport": "Transport",
        "healthcare": "Healthcare",
        "education": "Education",
        "other": "Other",
    },
    "pl": {
        "housing": "Mieszkanie",
        "utilities": "Media",
        "insurance": "Ubezpieczenie",
        "subscriptions": "Subskrypcje",
        "entertainment": "Rozrywka",
        "transport": "Transport",
        "healthcare": "Zdrowie",
        "education": "Edukacja",
        "other": "Inne",
    },
    "de": {
        "housing": "Wohnen",
        "utilities": "Versorgung",
        "insurance": "Versicherung",
        "subscriptions": "Abonnements",
        "entertainment": "Unterhaltung",
        "transport": "Transport",
        "healthcare": "Gesundheit",
        "education": "Bildung",
        "other": "Sonstiges",
    },
}

DEFAULT_CATEGORY_NAMES: dict[str, str] = _CATEGORY_LABELS["en"]
_SUPPORTED_LANGUAGES = frozenset(_CATEGORY_LABELS)


class CategoryError(Exception):
    """Base class for service-level category failures.

    Routers map `status_code` onto the HTTP response.
    """

    status_code: int = 400


class CategoryNotFoundError(CategoryError):
    status_code = 404


class CategoryInvalidError(CategoryError):
    status_code = 422


class CategoryArchivedError(CategoryError):
    status_code = 422


class CategoryNameConflictError(CategoryError):
    status_code = 422


class CategoryInUseError(CategoryError):
    status_code = 400


class LabelableCategory(Protocol):
    name: str | None
    key: str | None


def category_label(language: str | None, category: LabelableCategory) -> str:
    """Rendered label: a custom/renamed name, else the translated default key."""
    if category.name:
        return category.name
    if category.key:
        lang = language if language in _SUPPORTED_LANGUAGES else "en"
        labels = _CATEGORY_LABELS[lang]
        return labels.get(category.key, category.key)
    return ""


def ensure_default_categories(db: Session, user: User) -> None:
    """Idempotently create any of the nine defaults the user is missing.

    Called on registration and from `GET /categories` so users migrated before
    this table existed (or who somehow lost a row) always have their defaults.
    """
    existing = {
        row[0]
        for row in db.query(Category.key)
        .filter(Category.user_id == user.id, Category.key.isnot(None))
        .all()
    }
    for key in DEFAULT_CATEGORY_KEYS:
        if key not in existing:
            db.add(Category(user_id=user.id, key=key))
    db.flush()


def list_categories(
    db: Session, user_id: int, *, include_archived: bool = False
) -> list[Category]:
    """Categories in stable order: defaults first, then customs, each by label."""
    label = func.coalesce(Category.name, Category.key)
    query = db.query(Category).filter(Category.user_id == user_id)
    if not include_archived:
        query = query.filter(Category.is_archived.is_(False))
    return query.order_by(Category.key.is_(None), label, Category.id).all()


def get_for_user(
    db: Session, user_id: int, category_id: int, *, allow_archived: bool = False
) -> Category:
    category = db.get(Category, category_id)
    if category is None or category.user_id != user_id:
        raise CategoryNotFoundError("Category not found")
    if category.is_archived and not allow_archived:
        raise CategoryArchivedError("Category is archived")
    return category


def _find_by_name(
    db: Session, user_id: int, name: str, *, exclude_id: int | None = None
) -> Category | None:
    query = db.query(Category).filter(
        Category.user_id == user_id,
        func.lower(Category.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.filter(Category.id != exclude_id)
    return query.first()


def create_category(db: Session, user_id: int, name: str) -> Category:
    """Create a custom category, rejecting case-insensitive duplicate names."""
    cleaned = name.strip()
    if not cleaned:
        raise CategoryInvalidError("Category name must not be blank")
    if _find_by_name(db, user_id, cleaned) is not None:
        raise CategoryNameConflictError("A category with this name already exists")
    category = Category(user_id=user_id, name=cleaned)
    db.add(category)
    db.flush()
    return category


def rename_category(db: Session, user_id: int, category_id: int, name: str) -> Category:
    category = get_for_user(db, user_id, category_id, allow_archived=True)
    cleaned = name.strip()
    if not cleaned:
        raise CategoryInvalidError("Category name must not be blank")
    if _find_by_name(db, user_id, cleaned, exclude_id=category.id) is not None:
        raise CategoryNameConflictError("A category with this name already exists")
    category.name = cleaned
    db.flush()
    return category


def set_archived(
    db: Session, user_id: int, category_id: int, is_archived: bool
) -> Category:
    category = get_for_user(db, user_id, category_id, allow_archived=True)
    category.is_archived = is_archived
    db.flush()
    return category


def delete_category(db: Session, user_id: int, category_id: int) -> None:
    """Hard-delete an unused category; refuse while any template references it."""
    category = get_for_user(db, user_id, category_id, allow_archived=True)
    in_use = (
        db.query(BillTemplate.id)
        .filter(BillTemplate.category_id == category.id)
        .first()
    )
    if in_use is not None:
        raise CategoryInUseError(
            "Category is used by existing bills; archive it instead"
        )
    db.delete(category)
    db.flush()


def _find_or_create_default(db: Session, user_id: int, key: str) -> Category:
    category = (
        db.query(Category)
        .filter(Category.user_id == user_id, Category.key == key)
        .first()
    )
    if category is None:
        category = Category(user_id=user_id, key=key)
        db.add(category)
        db.flush()
    return category


def resolve_legacy_key(db: Session, user_id: int, key: str) -> Category:
    """Resolve the legacy `category` string to the user's default category.

    Unknown keys are rejected so old clients cannot invent categories.
    """
    if key not in DEFAULT_CATEGORY_KEYS:
        raise CategoryInvalidError(f"Unknown category '{key}'")
    return _find_or_create_default(db, user_id, key)


def resolve_backup_value(db: Session, user_id: int, value: str | None) -> Category:
    """Resolve a backup `category` string (default key or custom name).

    Default keys map to that key's row (created if missing); anything else is
    treated as a custom name (case-insensitive find, else created). An absent
    or blank value falls back to the user's `other` category.
    """
    if value is None or not value.strip():
        return _find_or_create_default(db, user_id, "other")
    cleaned = value.strip()
    if cleaned in DEFAULT_CATEGORY_KEYS:
        return _find_or_create_default(db, user_id, cleaned)
    existing = _find_by_name(db, user_id, cleaned)
    if existing is not None:
        return existing
    category = Category(user_id=user_id, name=cleaned)
    db.add(category)
    db.flush()
    return category
