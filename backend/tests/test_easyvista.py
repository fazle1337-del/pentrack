"""EasyVista integration tests — no live tenant required.

These drive `app.services.easyvista` through an httpx.MockTransport that returns
the documented responses (201 HREF, 401, 406), asserting the request we build
and the reference we parse. Run from the backend/ dir:

    pip install -r requirements.txt -r requirements-dev.txt
    pytest

`get_settings()` is lru_cached, so mutating the returned object configures the
module-level `settings` the service already holds a reference to.
"""

import json

import httpx
import pytest

from app.core.config import get_settings
from app.models.models import Finding
from app.services import easyvista


def _configure():
    s = get_settings()
    s.easyvista_enabled = True
    s.easyvista_host = "https://acme.easyvista.com"
    s.easyvista_account = "50012"
    s.easyvista_catalog_guid = "GUID-123"
    s.easyvista_requestor_mail = "pentrack@acme.com"
    s.easyvista_login = "api-account"
    s.easyvista_password = "s3cret"


def _finding():
    return Finding(
        id=42,
        vulnerability="SQL Injection in login form",
        finding_description="Unparameterised query in /login.",
        asset_tested="web01",
    )


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_create_request_maps_body_and_parses_reference():
    _configure()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={"HREF": "https://acme.easyvista.com/api/v1/50012/requests/987"},
        )

    result = easyvista.create_request(_finding(), client=_client(handler))

    assert result["reference"] == "987"
    assert captured["url"].endswith("/api/v1/50012/requests")
    body = captured["body"]
    assert body["catalog_guid"] == "GUID-123"
    assert body["external_reference"] == "pentrack-finding-42"
    assert body["title"] == "SQL Injection in login form"
    assert body["requestor_mail"] == "pentrack@acme.com"


def test_401_raises_easyvista_error():
    _configure()
    handler = lambda r: httpx.Response(401, json={"error": "Invalid Login / Password"})
    with pytest.raises(easyvista.EasyVistaError, match="401"):
        easyvista.create_request(_finding(), client=_client(handler))


def test_406_raises_recipient_error():
    _configure()
    handler = lambda r: httpx.Response(406, text="recipient missing")
    with pytest.raises(easyvista.EasyVistaError, match="406"):
        easyvista.create_request(_finding(), client=_client(handler))


def test_missing_catalog_is_a_config_error():
    _configure()
    get_settings().easyvista_catalog_guid = ""
    get_settings().easyvista_catalog_code = ""
    handler = lambda r: httpx.Response(201, json={"HREF": ".../requests/1"})
    with pytest.raises(easyvista.EasyVistaError, match="catalog"):
        easyvista.create_request(_finding(), client=_client(handler))
