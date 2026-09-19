"""L1 — permissions: уровни доступа к командам."""

from __future__ import annotations

from typing import Iterable, Set

GUEST = 0
USER = 1
ADMIN = 2
OWNER = 3

_NAMES = {GUEST: "guest", USER: "user", ADMIN: "admin", OWNER: "owner"}


class PermissionManager:
    def __init__(self, owner_id: int, admins: Iterable[int] = ()) -> None:
        self.owner_id = owner_id
        self._admins: Set[int] = set(admins)

    def level(self, user_id: int) -> int:
        if user_id == self.owner_id:
            return OWNER
        if user_id in self._admins:
            return ADMIN
        if user_id != 0:
            return USER
        return GUEST

    def check(self, user_id: int, required: int = USER) -> bool:
        return self.level(user_id) >= required

    def add_admin(self, user_id: int) -> None:
        self._admins.add(user_id)

    def remove_admin(self, user_id: int) -> None:
        self._admins.discard(user_id)

    @staticmethod
    def name(level: int) -> str:
        return _NAMES.get(level, "unknown")
