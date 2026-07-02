"""Throwaway EasyVista stub for local end-to-end testing without a real tenant.

Mimics "create a request" plus the group/employee read endpoints, returning the
documented 201 HREF (or a 401/406 to exercise error paths). Point the app at it:

    # terminal 1 — run the stub on :9001
    uvicorn tests.easyvista_stub:app --port 9001

    # terminal 2 — configure the backend to use it, then start the app
    export EASYVISTA_ENABLED=true
    export EASYVISTA_HOST=http://127.0.0.1:9001
    export EASYVISTA_ACCOUNT=50012
    export EASYVISTA_CATALOG_GUID=GUID-LOCAL
    export EASYVISTA_REQUESTOR_MAIL=pentrack@local.test
    export EASYVISTA_BEARER_TOKEN=stub-token
    # ... then POST /itsm/findings/{id}/push as an admin.

Set STUB_STATUS=401 (or 406) in the stub's env to test failure handling. The
stub doesn't actually validate the bearer token — it's here to exercise the
request/response shape, not auth enforcement.
"""

import os

from fastapi import FastAPI, Request

app = FastAPI(title="EasyVista stub")

_counter = {"n": 1000}
_requests: dict[str, dict] = {}


@app.post("/api/v1/{account}/requests")
async def create_request(account: str, request: Request):
    status = int(os.getenv("STUB_STATUS", "201"))
    if status == 401:
        return _json(401, {"error": "Invalid or expired bearer token"})
    if status == 406:
        return _json(406, {"error": "recipient/requestor missing or unknown domain"})

    body = await request.json()
    _counter["n"] += 1
    req_id = str(_counter["n"])
    rfc_number = f"RFC{req_id.zfill(7)}"
    record = {"rfc_number": rfc_number, "STATUS_EN": "New"}
    # Indexed under both ids: real read/comment/close calls use rfc_number,
    # but the create-response follow-up GET (identifier gotcha) uses the
    # numeric REQUEST_ID — both need to resolve to the same ticket here.
    _requests[req_id] = record
    _requests[rfc_number] = record
    href = f"{str(request.base_url).rstrip('/')}/api/v1/{account}/requests/{req_id}"
    print(f"[stub] created request {req_id} ({rfc_number}) from body: {body}")
    return _json(201, {"HREF": href})


@app.get("/api/v1/{account}/requests/{request_id}")
async def get_request(account: str, request_id: str):
    data = _requests.get(request_id)
    if data is None:
        return _json(404, {"error": "not found"})
    resp = {"rfc_number": data["rfc_number"], "STATUS_EN": data["STATUS_EN"]}
    if os.getenv("STUB_CLOSED"):
        resp["END_DATE_UT"] = "2026-07-01T12:00:00Z"
        resp["STATUS_EN"] = "Closed"
    return _json(200, resp)


@app.get("/api/v1/{account}/groups")
async def list_groups(account: str):
    return _json(200, [{"GROUP_ID": "1", "GROUP_EN": "Web Team"}])


@app.get("/api/v1/{account}/groups/{group_id}")
async def get_group(account: str, group_id: str):
    return _json(200, {"GROUP_ID": group_id, "GROUP_EN": "Web Team"})


@app.get("/api/v1/{account}/groups/{group_id}/employees")
async def list_group_employees(account: str, group_id: str):
    return _json(200, [{"EMPLOYEE_ID": "42", "IDENTIFICATION": "S12345"}])


@app.get("/api/v1/{account}/employees/{employee_id}/groups")
async def list_employee_groups(account: str, employee_id: str):
    return _json(200, [{"GROUP_ID": "1", "GROUP_EN": "Web Team"}])


def _json(status: int, payload):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status, content=payload)
