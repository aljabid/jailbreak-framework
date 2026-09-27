from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    ADMINISTRATOR = "administrator"
    CAMPAIGN_AUTHOR = "campaign_author"
    CAMPAIGN_OPERATOR = "campaign_operator"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class Permission(str, Enum):
    CAMPAIGN_CREATE = "campaign:create"
    CAMPAIGN_RUN = "campaign:run"
    CAMPAIGN_VIEW = "campaign:view"
    CAMPAIGN_PAUSE = "campaign:pause"
    CAMPAIGN_CANCEL = "campaign:cancel"
    CAMPAIGN_PURGE = "campaign:purge"
    FINDING_REVIEW = "finding:review"
    FINDING_EXPORT = "finding:export"
    AUDIT_VIEW = "audit:view"
    BACKUP_CREATE = "backup:create"
    BACKUP_VERIFY = "backup:verify"
    AUTHORIZATION_SIGN = "authorization:sign"
    AUTHORIZATION_VERIFY = "authorization:verify"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMINISTRATOR: set(Permission),
    Role.CAMPAIGN_AUTHOR: {
        Permission.CAMPAIGN_CREATE,
        Permission.CAMPAIGN_VIEW,
    },
    Role.CAMPAIGN_OPERATOR: {
        Permission.CAMPAIGN_RUN,
        Permission.CAMPAIGN_VIEW,
        Permission.CAMPAIGN_PAUSE,
        Permission.CAMPAIGN_CANCEL,
    },
    Role.REVIEWER: {
        Permission.CAMPAIGN_VIEW,
        Permission.FINDING_REVIEW,
        Permission.FINDING_EXPORT,
    },
    Role.AUDITOR: {
        Permission.CAMPAIGN_VIEW,
        Permission.AUDIT_VIEW,
        Permission.FINDING_EXPORT,
        Permission.BACKUP_VERIFY,
        Permission.AUTHORIZATION_VERIFY,
    },
    Role.VIEWER: {Permission.CAMPAIGN_VIEW},
}


@dataclass(frozen=True, slots=True)
class AccessContext:
    actor_id: str
    role: Role

    def __post_init__(self) -> None:
        if not self.actor_id.strip():
            raise ValueError("actor_id must not be blank")

    @classmethod
    def from_environment(cls) -> AccessContext:
        actor_id = os.getenv("JBF_ACTOR_ID", "")
        raw_role = os.getenv("JBF_ACTOR_ROLE", "")
        if not actor_id or not raw_role:
            raise PermissionError("JBF_ACTOR_ID and JBF_ACTOR_ROLE are required")
        try:
            role = Role(raw_role)
        except ValueError as exc:
            raise PermissionError(f"Unknown actor role: {raw_role}") from exc
        return cls(actor_id=actor_id, role=role)

    def require(self, permission: Permission) -> None:
        if permission not in ROLE_PERMISSIONS[self.role]:
            raise PermissionError(
                f"Actor {self.actor_id} with role {self.role.value} "
                f"lacks permission {permission.value}"
            )
