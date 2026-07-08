from dataclasses import dataclass, field
from typing import Callable

from .qt import QWidget


PageFactory = Callable[[], QWidget]


@dataclass(frozen=True)
class PageDescriptor:
    key: str
    title: str
    section: str | None
    icon_names: tuple[str, ...]
    factory: PageFactory
    search_description: str = ""
    search_terms: tuple[str, ...] = field(default_factory=tuple)
    profile: str = "all"

    @property
    def searchable_text(self) -> str:
        return " ".join((self.key, self.title, self.search_description, *self.search_terms)).lower()


def descriptor_from_nav_item(
    *,
    section: str | None,
    icon_names: tuple[str, ...],
    key: str,
    title: str,
    factory: PageFactory,
    search_metadata: tuple[str, str, list[str]] | None = None,
) -> PageDescriptor:
    if search_metadata is None:
        return PageDescriptor(
            key=key,
            title=title,
            section=section,
            icon_names=icon_names,
            factory=factory,
        )
    search_title, description, terms = search_metadata
    return PageDescriptor(
        key=key,
        title=search_title or title,
        section=section,
        icon_names=icon_names,
        factory=factory,
        search_description=description,
        search_terms=tuple(terms),
    )


def descriptors_from_nav_groups(nav_groups, search_metadata) -> list[PageDescriptor]:
    descriptors: list[PageDescriptor] = []
    for section, items in nav_groups:
        for icon_names, key, title, _description, factory in items:
            descriptors.append(
                descriptor_from_nav_item(
                    section=section,
                    icon_names=tuple(icon_names),
                    key=key,
                    title=title,
                    factory=factory,
                    search_metadata=search_metadata.get(key),
                )
            )
    return descriptors


def visible_for_profile(descriptor: PageDescriptor, profile: str) -> bool:
    if descriptor.profile == "gaming":
        return profile == "gaming"
    if descriptor.profile == "work":
        return profile == "work"
    return True
