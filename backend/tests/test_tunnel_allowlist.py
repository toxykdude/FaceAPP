"""
Tunnel allowlist tests (task 4.6/4.7).

The enforcement point is the cloudflared ingress on LXC 114 — this repo ships
the config artifact (``scripts/cloudflared/config.yml``) plus this test, which
replicates cloudflared's ingress decision semantics (first matching rule wins;
``path`` is an unanchored regex searched against the request path — Go RE2
``MatchString`` semantics, equivalent to Python ``re.search``) and asserts the
allowed/denied decision for every route class in design.md's public allowlist:

    ALLOWED: GET /api/health, POST /api/auth/member-{login,verify,resend},
             /api/portal/*
    DENIED:  everything else — explicitly /cv/*, /api/cv/*, /api/health/db,
             /api/health/full, /api/health/redis, all admin API routes.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "scripts" / "cloudflared" / "config.yml"
DENY_SERVICE = "http_status:404"
# RFC 2606 reserved domain — the shipped config must use placeholders, never
# real hostnames or secrets.
PLACEHOLDER_SUFFIX = ".example.com"


@pytest.fixture(scope="module")
def ingress_rules():
    doc = yaml.safe_load(CONFIG_PATH.read_text())
    assert (
        isinstance(doc.get("ingress"), list) and doc["ingress"]
    ), "config must define a non-empty ingress rule list"
    return doc["ingress"]


def route_decision(rules, path, hostname):
    """First-match-wins routing exactly as cloudflared evaluates ingress."""
    for rule in rules:
        rule_host = rule.get("hostname")
        if rule_host is not None and rule_host != hostname:
            continue
        rule_path = rule.get("path")
        if rule_path is not None:
            import re

            if not re.search(rule_path, path):
                continue
        return rule["service"]
    raise AssertionError(f"no ingress rule matched {path!r} — missing catch-all")


def assert_allowed(rules, path, backend_service):
    assert (
        route_decision(rules, path, "portal.example.com") == backend_service
    ), f"{path} must route to the backend service"


def assert_denied(rules, path):
    assert (
        route_decision(rules, path, "portal.example.com") == DENY_SERVICE
    ), f"{path} must fall through to the 404 catch-all"


class TestIngressStructure:
    def test_final_rule_is_catch_all_404(self, ingress_rules):
        """cloudflared REQUIRES a final catch-all rule; ours denies."""
        last = ingress_rules[-1]
        assert "hostname" not in last and "path" not in last
        assert last["service"] == DENY_SERVICE

    def test_allowed_rules_target_loopback_backend_only(self, ingress_rules):
        """Every non-catch-all rule must point at the same loopback backend
        origin (no other origin, no scheme upgrades to sneak past review)."""
        allow_rules = [r for r in ingress_rules if r is not ingress_rules[-1]]
        assert allow_rules, "expected at least one allow rule"
        services = {r["service"] for r in allow_rules}
        assert services == {"http://127.0.0.1:8000"}, services

    def test_hostname_is_a_placeholder(self, ingress_rules):
        """No real hostnames or secrets in the shipped artifact."""
        for rule in ingress_rules:
            host = rule.get("hostname")
            if host is not None:
                assert host.endswith(PLACEHOLDER_SUFFIX), host


class TestAllowedRoutes:
    def test_basic_health_reachable(self, ingress_rules):
        assert_allowed(ingress_rules, "/api/health", "http://127.0.0.1:8000")

    @pytest.mark.parametrize(
        "path",
        [
            "/api/auth/member-login",
            "/api/auth/member-verify",
            "/api/auth/member-resend",
        ],
    )
    def test_member_auth_routes_reachable(self, ingress_rules, path):
        assert_allowed(ingress_rules, path, "http://127.0.0.1:8000")

    @pytest.mark.parametrize(
        "path",
        [
            "/api/portal/me",
            "/api/portal/plans",
            "/api/portal/renew",
            "/api/portal/webhook-renew",
            "/api/portal/pending-payment",
        ],
    )
    def test_portal_routes_reachable(self, ingress_rules, path):
        assert_allowed(ingress_rules, path, "http://127.0.0.1:8000")


class TestDeniedRoutes:
    @pytest.mark.parametrize(
        "path",
        [
            "/cv/templates",
            "/cv/members/00000000-0000-0000-0000-000000000000",
            "/api/cv/templates",
            "/api/cv/invalidate/00000000-0000-0000-0000-000000000000",
        ],
    )
    def test_cv_and_internal_routes_denied(self, ingress_rules, path):
        assert_denied(ingress_rules, path)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/health/db",
            "/api/health/full",
            "/api/health/redis",
        ],
    )
    def test_deep_health_endpoints_denied(self, ingress_rules, path):
        assert_denied(ingress_rules, path)

    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/api-status",
            "/docs",
            "/openapi.json",
            "/api/members",
            "/api/users",
            "/api/sales/dashboard",
            "/api/system/db-export",
            "/api/system/backup-config",
        ],
    )
    def test_admin_and_static_routes_denied(self, ingress_rules, path):
        assert_denied(ingress_rules, path)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/healthx",
            "/api/health/dbb",
            "/api/auth/member-loginX",
            "/api/auth/member-login/extra",
            "/api/auth/member-logins/admin",
            "/api/portalx/me",
            "/api/portal",  # bare prefix without the slash is not a route
        ],
    )
    def test_near_misses_denied(self, ingress_rules, path):
        """Anchored regexes: suffix tricks must NOT widen the allowlist."""
        assert_denied(ingress_rules, path)
