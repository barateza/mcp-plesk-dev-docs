from enum import Enum
from typing import Literal, Union


class CategoryEnum(str, Enum):
    """Supported Plesk documentation categories."""

    GUIDE = "guide"
    CLI = "cli"
    API = "api"
    PHP_STUBS = "php-stubs"
    JS_SDK = "js-sdk"


VALID_CATEGORIES: frozenset[str] = frozenset(c.value for c in CategoryEnum)


def validate_category(category: str, allow_all: bool = False) -> None:
    """Validate that a category string is valid."""
    if allow_all and category == "all":
        return
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: '{category}'")


# Type alias for refresh_knowledge which accepts a specific category or "all"
CategoryOrAll = Union[CategoryEnum, Literal["all"]]
