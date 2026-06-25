"""Throwaway EasyVista stub for local end-to-end testing without a real tenant.

Mimics just the "create a request" endpoint, returning the documented 201 HREF
(or a 401/406 to exercise error paths). Point the app at it:

    # terminal 1 — run the stub on :9001
    uvicorn tests.easyvista_stub:app --port 9001

    # terminal 2 — configure the backend to use it, then start the app
    export EASYVISTA_ENABLED=true
    export EASYVISTA_HOST=http://127.0.0.1:9001
    export EASYVISTA_ACCOUNT=50012
    export EASYVISTA_CATALOG_GUID=GUID-LOCAL
    export EASYVISTA_REQUESTOR_MAIL=pentrack@local.test
    export EASYVISTA_LOGIN=api && export EASYVISTA_PASSWORD=stub
    # ... then POST /itsm/findings/{id}/push as an admin.

Set STUB_STATUS=401 (or 406) in the stub's env to test failure handling.
"""

import os

from fastapi import FastAPI, Request

app = FastAPI(title="EasyVista stub")

_counter = {"n": 1000}


@app.post("/api/v1/{account}/requests")
async def create_request(account: str, request: Request):
    status = int(os.getenv("STUB_STATUS", "201"))
    if status == 401:
        return _json(401, {"error": "Invalid Login / Password"})
    if status == 406:
        return _json(406, {"error": "recipient/requestor missing or unknown domain"})

    body = await request.json()
    _counter["n"] += 1
    req_id = _counter["n"]
    href = f"{str(request.base_url).rstrip('/')}/api/v1/{account}/requests/{req_id}"
    print(f"[stub] created request {req_id} from body: {body}")
    return _json(201, {"HREF": href})


def _json(status: int, payload: dict):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status, content=payload)
