from enum import Enum
from typing import Literal, Union


class CategoryEnum(str, Enum):
    """Supported Plesk documentation categories."""

    GUIDE = "guide"
    CLI = "cli"
    API = "api"
    PHP_STUBS = "php-stubs"
    JS_SDK = "js-sdk"


# Type alias for refresh_knowledge which accepts a specific category or "all"
CategoryOrAll = Union[CategoryEnum, Literal["all"]]
