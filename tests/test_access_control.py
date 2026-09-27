import pytest

from policy.access import AccessContext, Permission, Role


def test_administrator_has_every_permission():
    context = AccessContext("admin@example.test", Role.ADMINISTRATOR)
    for permission in Permission:
        context.require(permission)


def test_campaign_author_cannot_run_campaign():
    context = AccessContext("author@example.test", Role.CAMPAIGN_AUTHOR)
    context.require(Permission.CAMPAIGN_CREATE)
    with pytest.raises(PermissionError, match="lacks permission"):
        context.require(Permission.CAMPAIGN_RUN)


def test_viewer_is_read_only():
    context = AccessContext("viewer@example.test", Role.VIEWER)
    context.require(Permission.CAMPAIGN_VIEW)
    with pytest.raises(PermissionError):
        context.require(Permission.CAMPAIGN_CANCEL)


def test_environment_identity_is_default_deny(monkeypatch):
    monkeypatch.delenv("JBF_ACTOR_ID", raising=False)
    monkeypatch.delenv("JBF_ACTOR_ROLE", raising=False)
    with pytest.raises(PermissionError, match="required"):
        AccessContext.from_environment()


def test_environment_identity_is_parsed(monkeypatch):
    monkeypatch.setenv("JBF_ACTOR_ID", "operator@example.test")
    monkeypatch.setenv("JBF_ACTOR_ROLE", "campaign_operator")
    context = AccessContext.from_environment()
    assert context.role == Role.CAMPAIGN_OPERATOR
