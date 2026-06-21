"""Platform client base class and registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..discover import Article


@dataclass
class PublishResult:
    """Result of a publish or update operation."""
    post_id: str
    url: str
    platform: str


class PlatformClient(ABC):
    """Base class for platform publishing clients."""

    name: str = ""

    @abstractmethod
    def publish(self, article: Article, body: str, tags: list[str], cover_image_url: str) -> PublishResult:
        """Create a new post on the platform. Returns (id, url)."""
        ...

    @abstractmethod
    def update(self, article: Article, body: str, tags: list[str], cover_image_url: str, existing_id: str) -> PublishResult:
        """Update an existing post on the platform. Returns (id, url)."""
        ...

    @property
    def supports_update(self) -> bool:
        return True


def get_platform_registry() -> dict[str, type[PlatformClient]]:
    """Lazy import to avoid circular deps and allow partial configs."""
    from .devto import DevToClient
    from .hashnode import HashnodeClient
    from .medium import MediumClient
    return {
        "devto": DevToClient,
        "hashnode": HashnodeClient,
        "medium": MediumClient,
    }
