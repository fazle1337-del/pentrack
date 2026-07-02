"""EasyVista Service Manager (ITSM) integration.

OPTIONAL and OFF by default (`easyvista_enabled`), mirroring the SSO rollout: the
code ships dark and is validated against a real tenant later. Create-request
speaks the documented REST contract:

    POST {host}/api/v1/{account}/requests
    -> 201 {"HREF": ".../requests/{id}"}

(see https://docs.easyvista.com/docs/rest-api-create-an-incident-request).

The entire EasyVista surface lives in this one module: that isolation IS the
adapter boundary — retarget a different ITSM by swapping this file, without
touching findings or routers. No abstract base class until a second backend
actually exists (keep it minimal).

Built without a live EasyVista tenant: the HTTP client is injectable so tests
drive it with an httpx.MockTransport (see backend/tests/test_easyvista.py), and a
local stub (backend/tests/easyvista_stub.py) exercises the full path by hand.

Auth (2026-07-01, confirmed by the EV technician): a bearer token tied to a
managed EV identity, resolved DB-over-env via app/core/easyvista_config.py —
NOT HTTP Basic, which was this scaffold's original (unconfirmed) assumption.

Still open before enabling against a real tenant: the tenant-specific
catalog_guid and any risk-rating -> EV urgency/severity ID mapping (tenant-
specific, deliberately left out rather than guessed).
"""

from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.easyvista_config import get_easyvista_bearer_token
from app.models.models import Finding

settings = get_settings()


class EasyVistaError(Exception):
    """Raised on any configuration or API failure when calling EasyVista."""


def _base_url() -> str:
    if not settings.easyvista_host or not settings.easyvista_account:
        raise EasyVistaError("EasyVista host/account is not configured")
    base = settings.easyvista_host.rstrip("/")
    return f"{base}/api/v1/{settings.easyvista_account}"


def _requests_url() -> str:
    return f"{_base_url()}/requests"


def _auth_headers(db: Session | None) -> dict:
    token = get_easyvista_bearer_token(db) if db is not None else settings.easyvista_bearer_token
    if not token:
        raise EasyVistaError("EasyVista bearer token is not configured")
    return {"Authorization": f"Bearer {token}"}


def _describe(finding: Finding) -> str:
    """Human-readable body assembled from the finding's fields."""
    parts: list[str] = []
    if finding.asset_tested:
        parts.append(f"Asset: {finding.asset_tested}")
    if finding.net_rating:
        parts.append(f"Net risk: {finding.net_rating.value}")
    if finding.finding_description:
        parts.append(finding.finding_description)
    if finding.test_vendor_initial_recommendation:
        parts.append(f"Recommendation: {finding.test_vendor_initial_recommendation}")
    parts.append(f"PenTrack finding #{finding.id}")
    return "\n\n".join(parts)


def _build_body(finding: Finding, *, ev_group_id: str | None = None) -> dict:
    """Map a finding onto the EasyVista request payload.

    Only `catalog_guid`/`catalog_code` is strictly required by the API; the rest
    is best-effort. Risk-rating -> EV urgency/severity IDs is intentionally left
    out: those IDs are tenant-specific, so wire them once a real catalogue is
    known rather than guessing here.

    `ev_group_id`, when given, is stamped as `group_id` — EV's assignment
    field (confirmed against the wiki's Q2 answer). The caller (routers/itsm.py)
    is responsible for resolving it from the finding's owning Team and for
    deciding what to do when there isn't one (assignment is group-based; an
    individually-owned finding has no EV group to route to).
    """
    body: dict = {}
    if settings.easyvista_catalog_guid:
        body["catalog_guid"] = settings.easyvista_catalog_guid
    elif settings.easyvista_catalog_code:
        body["catalog_code"] = settings.easyvista_catalog_code
    else:
        raise EasyVistaError("EasyVista catalog_guid/catalog_code is not configured")

    if settings.easyvista_requestor_mail:
        # EV 406s without a recipient/requestor whose domain it recognises.
        body["requestor_mail"] = settings.easyvista_requestor_mail
        body["recipient_mail"] = settings.easyvista_requestor_mail

    if ev_group_id:
        body["group_id"] = ev_group_id

    # Correlate the EV request back to this finding (stable across re-pushes).
    body["external_reference"] = f"pentrack-finding-{finding.id}"
    if finding.vulnerability:
        body["title"] = finding.vulnerability[:255]
    body["description"] = _describe(finding)
    return body


def _reference_from_href(href: str) -> str:
    """EV returns {"HREF": ".../requests/{id}"}; the trailing id is the REQUEST_ID."""
    return href.rstrip("/").rsplit("/", 1)[-1] if href else ""


def _get(db: Session | None, path: str, *, client: httpx.Client | None = None):
    """Shared GET helper for the read-only EV endpoints below."""
    url = f"{_base_url()}{path}"
    headers = _auth_headers(db)

    owns_client = client is None
    client = client or httpx.Client(timeout=settings.easyvista_timeout_seconds)
    try:
        resp = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise EasyVistaError(f"EasyVista request failed: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 401:
        raise EasyVistaError("EasyVista rejected the bearer token (401)")
    if resp.status_code == 404:
        raise EasyVistaError(f"EasyVista resource not found (404): {path}")
    raise EasyVistaError(
        f"EasyVista returned an unexpected status {resp.status_code}: {resp.text}"
    )


def _fetch_rfc_number(
    request_id: str, db: Session | None, *, client: httpx.Client | None = None
) -> str:
    """Look up the rfc_number for a just-created request.

    create_request only gets REQUEST_ID out of the create response's HREF, but
    read/comment/close key off rfc_number instead (the "identifier gotcha" —
    see CLAUDE.md). ASSUMPTION, unverified against a live tenant (like the auth
    mechanism was before it): GET /requests/{id} accepts REQUEST_ID as well as
    rfc_number as the path parameter. Confirm once EV access exists; if wrong,
    this lookup needs adjusting.
    """
    data = _get(db, f"/requests/{request_id}", client=client)
    return data.get("rfc_number") or data.get("RFC_NUMBER") or request_id


def get_request_status(
    rfc_number: str, db: Session | None = None, *, client: httpx.Client | None = None
) -> dict:
    """GET /requests/{rfc_number} — current status label + closed state.

    Returns {"status_label", "status_guid", "closed"}. `closed` is derived
    from EV's END_DATE_UT being set — the wiki's confirmed authoritative
    closed signal, *not* a match against status label/enum values. ASSUMPTION,
    unverified against a live tenant (same caveat as `_fetch_rfc_number`):
    tries a few plausible casings for the field name; if none are present in
    the response, `closed` comes back None (unknown) rather than guessing.
    """
    data = _get(db, f"/requests/{rfc_number}", client=client)
    end_date = data.get("END_DATE_UT") or data.get("end_date_ut") or data.get("END_DATE")
    return {
        "status_label": data.get("STATUS_EN") or data.get("status_en"),
        "status_guid": data.get("STATUS_GUID") or data.get("status_guid"),
        "closed": bool(end_date) if end_date is not None else None,
    }


def _parse_datetime(raw) -> datetime | None:
    """Best-effort ISO-8601 parse; EV's exact date format is unverified
    against a live tenant, so a value that doesn't parse is dropped (None)
    rather than raising."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_request_comments(
    rfc_number: str, db: Session | None = None, *, client: httpx.Client | None = None
) -> list[dict]:
    """GET /requests/comment/{rfc_number} — the ticket's comment thread.

    A "comment" is an EV **action** of a specific AM_ACTION_TYPE (the ticket
    description itself is the first comment — wiki "EasyVista integration —
    open questions", locked decisions). ASSUMPTION, unverified against a live
    tenant (same caveat as `get_request_status`): field names/casing are
    guessed from the documented conventions elsewhere in this module; any
    field that isn't present under a tried key comes back None rather than
    guessing further. `closed` mirrors the ticket-level convention — action
    END_DATE_UT being set, not a status/label match.

    Returns a list of dicts: {ev_action_id, author, body, action_type,
    posted_at, closed}, in the order EV returns them.
    """
    data = _get(db, f"/requests/comment/{rfc_number}", client=client)
    rows = data if isinstance(data, list) else data.get("actions") or data.get("ACTIONS") or []

    comments = []
    for row in rows:
        author = (
            row.get("contact_name")
            or row.get("CONTACT_NAME")
            or row.get("contact_email")
            or row.get("CONTACT_EMAIL")
        )
        end_date = row.get("END_DATE_UT") or row.get("end_date_ut") or row.get("END_DATE")
        comments.append(
            {
                "ev_action_id": row.get("ACTION_ID") or row.get("action_id"),
                "author": author,
                "body": row.get("DESCRIPTION") or row.get("description") or row.get("COMMENT"),
                "action_type": row.get("AM_ACTION_TYPE") or row.get("action_type"),
                "posted_at": _parse_datetime(
                    row.get("CREATION_DATE") or row.get("creation_date")
                ),
                "closed": bool(end_date) if end_date is not None else None,
            }
        )
    return comments


def create_request(
    finding: Finding,
    *,
    db: Session | None = None,
    client: httpx.Client | None = None,
    ev_group_id: str | None = None,
) -> dict:
    """POST a finding to EasyVista as a request. Returns {"reference", "href"}.

    `client` is injectable so tests can supply an httpx.MockTransport without a
    live tenant. `db` resolves the bearer token DB-over-env (see
    app/core/easyvista_config.py); pass None to force the env-only fallback.
    `reference` is the rfc_number (fetched via a follow-up GET right after
    create), not the REQUEST_ID from the HREF — see `_fetch_rfc_number`.
    `ev_group_id` is stamped onto the request as the assignee group — see
    `_build_body`.
    """
    url = _requests_url()
    body = _build_body(finding, ev_group_id=ev_group_id)
    headers = _auth_headers(db)

    owns_client = client is None
    client = client or httpx.Client(timeout=settings.easyvista_timeout_seconds)
    try:
        try:
            resp = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise EasyVistaError(f"EasyVista request failed: {exc}") from exc

        if resp.status_code == 201:
            href = resp.json().get("HREF", "")
            request_id = _reference_from_href(href)
            reference = request_id
            if request_id:
                try:
                    # Reuses `client` — must still be open, hence the shared
                    # try/finally below rather than closing right after POST
                    # (a bug caught in manual end-to-end testing: closing here
                    # broke every real push, since owns_client is only False
                    # in tests that inject their own client).
                    reference = _fetch_rfc_number(request_id, db, client=client)
                except EasyVistaError:
                    # The ticket was already created in EV — don't lose that
                    # side effect over a failed follow-up lookup. `reference`
                    # already holds the (possibly wrong, per the identifier
                    # gotcha) REQUEST_ID, so keep it.
                    pass
            return {"reference": reference, "href": href}
        if resp.status_code == 401:
            raise EasyVistaError("EasyVista rejected the bearer token (401)")
        if resp.status_code == 406:
            raise EasyVistaError(
                "EasyVista rejected the requestor/recipient (406) — confirm the "
                "email domain is known to the tenant"
            )
        raise EasyVistaError(
            f"EasyVista returned an unexpected status {resp.status_code}: {resp.text}"
        )
    finally:
        if owns_client:
            client.close()


def list_groups(db: Session | None = None, *, client: httpx.Client | None = None) -> list:
    """GET /groups — for admins mapping a pentrack Team to Team.ev_group_id."""
    return _get(db, "/groups", client=client)


def get_group(
    group_id: str, db: Session | None = None, *, client: httpx.Client | None = None
) -> dict:
    """GET /groups/{group_id}."""
    return _get(db, f"/groups/{group_id}", client=client)


def list_group_employees(
    group_id: str, db: Session | None = None, *, client: httpx.Client | None = None
) -> list:
    """GET /groups/{group_id}/employees."""
    return _get(db, f"/groups/{group_id}/employees", client=client)


def list_employee_groups(
    employee_id: str, db: Session | None = None, *, client: httpx.Client | None = None
) -> list:
    """GET /employees/{employee_id}/groups."""
    return _get(db, f"/employees/{employee_id}/groups", client=client)


def push_finding(
    db: Session,
    finding: Finding,
    *,
    client: httpx.Client | None = None,
    ev_group_id: str | None = None,
) -> dict:
    """Create the EV request and persist its reference onto the finding."""
    result = create_request(finding, db=db, client=client, ev_group_id=ev_group_id)
    finding.itsm_reference = result["reference"]
    db.commit()
    db.refresh(finding)
    return result
