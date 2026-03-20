"""
Tests for social_media.check_platform()

Mocks requests.get so no real HTTP calls are made.
Run with:  python -m pytest tests/test_social_media.py -v
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from modules.social_media import check_platform, _is_redirect_url, PLATFORMS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(
    status_code: int = 200,
    text: str = "<html>" + "x" * 2000 + "</html>",
    final_url: str | None = None,
    url: str = "https://example.com/user/foo",
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.url = final_url or url
    return resp


GITHUB = next(p for p in PLATFORMS if p["name"] == "GitHub")
HACKERNEWS = next(p for p in PLATFORMS if p["name"] == "HackerNews")
STEAM = next(p for p in PLATFORMS if p["name"] == "Steam")


# ── _is_redirect_url ─────────────────────────────────────────────────────────

class TestIsRedirectUrl:
    def test_same_path_is_not_redirect(self):
        assert not _is_redirect_url(
            "https://github.com/johndoe",
            "https://github.com/johndoe",
        )

    def test_different_domain_is_redirect(self):
        assert _is_redirect_url(
            "https://www.linkedin.com/in/johndoe",
            "https://www.linkedin.com/login",
        )

    def test_login_path_is_redirect(self):
        assert _is_redirect_url(
            "https://twitter.com/johndoe",
            "https://twitter.com/login",
        )

    def test_home_path_is_redirect(self):
        assert _is_redirect_url(
            "https://example.com/user/johndoe",
            "https://example.com/",
        )

    def test_signup_path_is_redirect(self):
        assert _is_redirect_url(
            "https://example.com/user/johndoe",
            "https://example.com/signup",
        )

    def test_auth_path_is_redirect(self):
        assert _is_redirect_url(
            "https://example.com/user/foo",
            "https://example.com/auth/login",
        )

    def test_unrelated_deep_path_not_redirect(self):
        assert not _is_redirect_url(
            "https://github.com/johndoe",
            "https://github.com/johndoe?tab=repositories",
        )


# ── check_platform ────────────────────────────────────────────────────────────

class TestCheckPlatform:

    def test_404_returns_not_found(self):
        with patch("requests.get", return_value=_mock_response(status_code=404)):
            result = check_platform("nobody", GITHUB)
        assert result["state"] == "not_found"

    def test_403_returns_blocked(self):
        with patch("requests.get", return_value=_mock_response(status_code=403)):
            result = check_platform("nobody", GITHUB)
        assert result["state"] == "blocked"

    def test_429_returns_blocked(self):
        with patch("requests.get", return_value=_mock_response(status_code=429)):
            result = check_platform("nobody", GITHUB)
        assert result["state"] == "blocked"

    def test_500_returns_error(self):
        with patch("requests.get", return_value=_mock_response(status_code=500)):
            result = check_platform("nobody", GITHUB)
        assert result["state"] == "error"

    def test_not_found_text_in_body(self):
        body = "<html>" + "x" * 2000 + "Not Found" + "</html>"
        resp = _mock_response(
            text=body,
            final_url="https://github.com/nobody",
            url="https://github.com/nobody",
        )
        with patch("requests.get", return_value=resp):
            result = check_platform("nobody", GITHUB)
        assert result["state"] == "not_found"

    def test_redirect_to_login_returns_redirected(self):
        resp = _mock_response(
            status_code=200,
            final_url="https://github.com/login",
            url="https://github.com/nobody",
        )
        with patch("requests.get", return_value=resp):
            result = check_platform("nobody", GITHUB)
        assert result["state"] == "redirected"

    def test_body_too_short_returns_not_found(self):
        resp = _mock_response(
            status_code=200,
            text="<html>tiny</html>",
            final_url="https://github.com/johndoe",
            url="https://github.com/johndoe",
        )
        with patch("requests.get", return_value=resp):
            result = check_platform("johndoe", GITHUB)
        assert result["state"] == "not_found"

    def test_confirm_text_present_returns_confirmed(self):
        body = "<html>" + "repositories" * 100 + "</html>"
        resp = _mock_response(
            text=body,
            final_url="https://github.com/johndoe",
            url="https://github.com/johndoe",
        )
        with patch("requests.get", return_value=resp):
            result = check_platform("johndoe", GITHUB)
        assert result["state"] == "confirmed"

    def test_no_confirm_text_but_ok_returns_possible(self):
        # GitHub needs "repositories" — remove it
        body = "<html>" + "profile page content here" * 100 + "</html>"
        resp = _mock_response(
            text=body,
            final_url="https://github.com/johndoe",
            url="https://github.com/johndoe",
        )
        with patch("requests.get", return_value=resp):
            result = check_platform("johndoe", GITHUB)
        assert result["state"] == "possible"

    def test_timeout_returns_error(self):
        import requests as _requests
        with patch("requests.get", side_effect=_requests.Timeout):
            result = check_platform("nobody", GITHUB)
        assert result["state"] == "error"
        assert "timeout" in result["note"]

    def test_hn_not_found_text(self):
        body = "<html>" + "No such user" * 10 + "</html>"
        resp = _mock_response(text=body)
        with patch("requests.get", return_value=resp):
            result = check_platform("nobody", HACKERNEWS)
        assert result["state"] == "not_found"

    def test_steam_confirm_text(self):
        # Body must be > _MIN_PROFILE_BYTES (800) to pass length guard
        body = "<html>" + "profile_header " * 100 + "</html>"
        resp = _mock_response(
            text=body,
            final_url="https://steamcommunity.com/id/johndoe",
            url="https://steamcommunity.com/id/johndoe",
        )
        with patch("requests.get", return_value=resp):
            result = check_platform("johndoe", STEAM)
        assert result["state"] == "confirmed"

    def test_result_always_has_required_keys(self):
        with patch("requests.get", return_value=_mock_response(status_code=404)):
            result = check_platform("x", GITHUB)
        assert "platform" in result
        assert "url" in result
        assert "state" in result
