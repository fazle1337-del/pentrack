"""EasyVista Service Manager (ITSM) integration — create a request from a finding.

OPTIONAL and OFF by default (`easyvista_enabled`), mirroring the SSO rollout: the
code ships dark and is validated against a real tenant later. It speaks the
documented "create a request" REST contract:

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
Two things must still be confirmed against a real tenant before enabling:
  1. auth mechanism — Basic is assumed (the doc only shows the 401 failure);
  2. the tenant-specific catalog_guid and any urgency/severity ID mapping.
"""

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.models import Finding

settings = get_settings()


class EasyVistaError(Exception):
    """Raised on any configuration or API failure when pushing to EasyVista."""


def _requests_url() -> str:
    if not settings.easyvista_host or not settings.easyvista_account:
        raise EasyVistaError("EasyVista host/account is not configured")
    base = settings.easyvista_host.rstrip("/")
    return f"{base}/api/v1/{settings.easyvista_account}/requests"


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


def _build_body(finding: Finding) -> dict:
    """Map a finding onto the EasyVista request payload.

    Only `catalog_guid`/`catalog_code` is strictly required by the API; the rest
    is best-effort. Risk-rating -> EV urgency/severity IDs is intentionally left
    out: those IDs are tenant-specific, so wire them once a real catalogue is
    known rather than guessing here.
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

    # Correlate the EV request back to this finding (stable across re-pushes).
    body["external_reference"] = f"pentrack-finding-{finding.id}"
    if finding.vulnerability:
        body["title"] = finding.vulnerability[:255]
    body["description"] = _describe(finding)
    return body


def _reference_from_href(href: str) -> str:
    """EV returns {"HREF": ".../requests/{id}"}; the trailing id is the reference."""
    return href.rstrip("/").rsplit("/", 1)[-1] if href else ""


def create_request(finding: Finding, *, client: httpx.Client | None = None) -> dict:
    """POST a finding to EasyVista as a request. Returns {"reference", "href"}.

    `client` is injectable so tests can supply an httpx.MockTransport without a
    live tenant. Auth is HTTP Basic with the integration account credentials.
    """
    url = _requests_url()
    body = _build_body(finding)
    auth = (settings.easyvista_login, settings.easyvista_password)

    owns_client = client is None
    client = client or httpx.Client(timeout=settings.easyvista_timeout_seconds)
    try:
        resp = client.post(url, json=body, auth=auth)
    except httpx.HTTPError as exc:
        raise EasyVistaError(f"EasyVista request failed: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    if resp.status_code == 201:
        href = resp.json().get("HREF", "")
        return {"reference": _reference_from_href(href), "href": href}
    if resp.status_code == 401:
        raise EasyVistaError("EasyVista rejected the integration credentials (401)")
    if resp.status_code == 406:
        raise EasyVistaError(
            "EasyVista rejected the requestor/recipient (406) — confirm the email "
            "domain is known to the tenant"
        )
    raise EasyVistaError(
        f"EasyVista returned an unexpected status {resp.status_code}: {resp.text}"
    )


def push_finding(
    db: Session, finding: Finding, *, client: httpx.Client | None = None
) -> dict:
    """Create the EV request and persist its reference onto the finding."""
    result = create_request(finding, client=client)
    finding.itsm_reference = result["reference"]
    db.commit()
    db.refresh(finding)
    return result
