from pydantic import BaseModel, Field, field_validator

_MAX_NAME_LENGTH = 50


def _clean_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("name must not be blank")
    if len(cleaned) > _MAX_NAME_LENGTH:
        raise ValueError(f"name must be at most {_MAX_NAME_LENGTH} characters")
    return cleaned


class CategoryOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    key: str | None
    name: str | None
    is_archived: bool


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=_MAX_NAME_LENGTH)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return _clean_name(value)


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=_MAX_NAME_LENGTH)
    is_archived: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_name(value)
