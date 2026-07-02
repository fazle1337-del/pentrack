"""EasyVista integration tests — no live tenant required.

These drive `app.services.easyvista` through an httpx.MockTransport that returns
the documented responses, asserting the requests we build and the responses we
parse. Run from the backend/ dir:

    pip install -r requirements.txt -r requirements-dev.txt
    pytest

`get_settings()` is lru_cached, so mutating the returned object configures the
module-level `settings` the service already holds a reference to. All calls
here pass `db=None`, which forces the env-only fallback (see
test_easyvista_config.py for the DB-over-env bearer-token resolution itself).
"""

import json
from datetime import datetime, timezone

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
    s.easyvista_bearer_token = "test-bearer-token"


def _finding():
    return Finding(
        id=42,
        vulnerability="SQL Injection in login form",
        finding_description="Unparameterised query in /login.",
        asset_tested="web01",
    )


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_create_request_sends_bearer_auth_maps_body_and_fetches_rfc_number():
    _configure()
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        if request.method == "POST":
            return httpx.Response(
                201,
                json={"HREF": "https://acme.easyvista.com/api/v1/50012/requests/987"},
            )
        # Follow-up GET to resolve rfc_number from REQUEST_ID (identifier gotcha).
        assert request.url.path.endswith("/requests/987")
        return httpx.Response(200, json={"rfc_number": "RFC0001234", "STATUS_EN": "New"})

    result = easyvista.create_request(_finding(), client=_client(handler))

    assert result["reference"] == "RFC0001234"  # rfc_number, not the raw REQUEST_ID
    assert len(requests_seen) == 2
    post, get = requests_seen
    assert post.method == "POST"
    assert post.headers["Authorization"] == "Bearer test-bearer-token"
    assert post.url.path.endswith("/api/v1/50012/requests")
    body = json.loads(post.content)
    assert body["catalog_guid"] == "GUID-123"
    assert body["external_reference"] == "pentrack-finding-42"
    assert body["title"] == "SQL Injection in login form"
    assert body["requestor_mail"] == "pentrack@acme.com"
    assert get.method == "GET"
    assert get.headers["Authorization"] == "Bearer test-bearer-token"


def test_ev_group_id_is_stamped_as_group_id_on_the_request():
    _configure()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["body"] = json.loads(request.content)
            return httpx.Response(201, json={"HREF": ".../requests/1"})
        return httpx.Response(200, json={"rfc_number": "RFC1"})

    easyvista.create_request(_finding(), client=_client(handler), ev_group_id="GRP-1")
    assert captured["body"]["group_id"] == "GRP-1"


def test_no_ev_group_id_omits_group_id_field():
    _configure()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["body"] = json.loads(request.content)
            return httpx.Response(201, json={"HREF": ".../requests/1"})
        return httpx.Response(200, json={"rfc_number": "RFC1"})

    easyvista.create_request(_finding(), client=_client(handler))
    assert "group_id" not in captured["body"]


def test_create_request_without_injected_client_survives_the_followup_get(monkeypatch):
    """Regression test: create_request used to close its own httpx.Client right
    after the POST, then reuse that closed client for the rfc_number follow-up
    GET. Every other test here injects a client (owns_client=False), which
    masked this — it only broke the real, client-less production path (caught
    via manual end-to-end testing against the local stub, not by this suite).
    This exercises that exact path by making the module create a client
    wired to the stub app in-process, with no client kwarg passed in."""
    _configure()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"HREF": ".../requests/987"})
        return httpx.Response(200, json={"rfc_number": "RFC0000987"})

    real_client_cls = httpx.Client

    def make_client(*args, **kwargs):
        # Same real httpx.Client the module would otherwise construct, just
        # wired to a MockTransport instead of the network — so this exercises
        # the actual owns_client=True path (construct, reuse across POST + the
        # follow-up GET, close exactly once), not a stand-in for it.
        return real_client_cls(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(easyvista.httpx, "Client", make_client)

    result = easyvista.create_request(_finding())  # no client= kwarg
    assert result["reference"].startswith("RFC")


def test_rfc_number_lookup_failure_falls_back_to_request_id():
    """The create side-effect already happened in EV — don't lose the reference
    entirely just because the follow-up GET failed."""
    _configure()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                201, json={"HREF": ".../requests/987"}
            )
        return httpx.Response(404, text="not found")

    result = easyvista.create_request(_finding(), client=_client(handler))
    assert result["reference"] == "987"


def test_401_raises_easyvista_error():
    _configure()
    handler = lambda r: httpx.Response(401, json={"error": "unauthorized"})
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


def test_missing_bearer_token_is_a_config_error():
    _configure()
    get_settings().easyvista_bearer_token = ""
    handler = lambda r: httpx.Response(201, json={"HREF": ".../requests/1"})
    with pytest.raises(easyvista.EasyVistaError, match="bearer token"):
        easyvista.create_request(_finding(), client=_client(handler))


def test_list_groups_sends_bearer_auth():
    _configure()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json=[{"GROUP_ID": "1", "GROUP_EN": "Web Team"}])

    result = easyvista.list_groups(client=_client(handler))

    assert result == [{"GROUP_ID": "1", "GROUP_EN": "Web Team"}]
    assert captured["url"].endswith("/api/v1/50012/groups")
    assert captured["auth"] == "Bearer test-bearer-token"


def test_get_group():
    _configure()
    handler = lambda r: httpx.Response(200, json={"GROUP_ID": "1", "GROUP_EN": "Web Team"})
    result = easyvista.get_group("1", client=_client(handler))
    assert result["GROUP_EN"] == "Web Team"


def test_list_group_employees():
    _configure()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[{"EMPLOYEE_ID": "42"}])

    result = easyvista.list_group_employees("1", client=_client(handler))
    assert result == [{"EMPLOYEE_ID": "42"}]
    assert captured["url"].endswith("/groups/1/employees")


def test_list_employee_groups():
    _configure()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[{"GROUP_ID": "1"}])

    result = easyvista.list_employee_groups("42", client=_client(handler))
    assert result == [{"GROUP_ID": "1"}]
    assert captured["url"].endswith("/employees/42/groups")


def test_group_lookup_404_raises_easyvista_error():
    _configure()
    handler = lambda r: httpx.Response(404, text="not found")
    with pytest.raises(easyvista.EasyVistaError, match="404"):
        easyvista.get_group("missing", client=_client(handler))


def test_get_request_status_open_ticket_has_no_end_date():
    _configure()
    handler = lambda r: httpx.Response(
        200, json={"STATUS_EN": "In Progress", "STATUS_GUID": "guid-1"}
    )
    result = easyvista.get_request_status("RFC0001", client=_client(handler))
    assert result == {"status_label": "In Progress", "status_guid": "guid-1", "closed": None}


def test_get_request_status_closed_ticket_has_end_date_set():
    _configure()
    handler = lambda r: httpx.Response(
        200,
        json={"STATUS_EN": "Closed", "STATUS_GUID": "guid-2", "END_DATE_UT": "2026-07-01T10:00:00Z"},
    )
    result = easyvista.get_request_status("RFC0001", client=_client(handler))
    assert result == {"status_label": "Closed", "status_guid": "guid-2", "closed": True}


def test_get_request_status_url_uses_rfc_number():
    _configure()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"STATUS_EN": "New"})

    easyvista.get_request_status("RFC0009999", client=_client(handler))
    assert captured["url"].endswith("/requests/RFC0009999")


def test_get_request_comments_parses_documented_fields():
    _configure()
    handler = lambda r: httpx.Response(
        200,
        json=[
            {
                "ACTION_ID": "1",
                "AM_ACTION_TYPE": "Description",
                "DESCRIPTION": "Original ticket description.",
                "contact_name": "pentrack",
                "CREATION_DATE": "2026-07-01T09:00:00Z",
            },
            {
                "ACTION_ID": "2",
                "AM_ACTION_TYPE": "Note",
                "DESCRIPTION": "Fixed.",
                "contact_name": "EV Tech",
                "CREATION_DATE": "2026-07-02T10:30:00Z",
                "END_DATE_UT": "2026-07-02T10:31:00Z",
            },
        ],
    )
    result = easyvista.get_request_comments("RFC0001", client=_client(handler))
    assert result == [
        {
            "ev_action_id": "1",
            "author": "pentrack",
            "body": "Original ticket description.",
            "action_type": "Description",
            "posted_at": datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
            "closed": None,
        },
        {
            "ev_action_id": "2",
            "author": "EV Tech",
            "body": "Fixed.",
            "action_type": "Note",
            "posted_at": datetime(2026, 7, 2, 10, 30, tzinfo=timezone.utc),
            "closed": True,
        },
    ]


def test_get_request_comments_degrades_missing_or_unrecognised_fields_to_none():
    _configure()
    handler = lambda r: httpx.Response(200, json=[{"UNRECOGNISED": "field"}])
    result = easyvista.get_request_comments("RFC0001", client=_client(handler))
    assert result == [
        {
            "ev_action_id": None,
            "author": None,
            "body": None,
            "action_type": None,
            "posted_at": None,
            "closed": None,
        }
    ]


def test_get_request_comments_url_uses_rfc_number():
    _configure()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    easyvista.get_request_comments("RFC0009999", client=_client(handler))
    assert captured["url"].endswith("/requests/comment/RFC0009999")
