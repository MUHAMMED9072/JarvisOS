from dataclasses import dataclass


@dataclass(slots=True)
class NavigationItem:
    name: str
    icon: str
    page: str
    