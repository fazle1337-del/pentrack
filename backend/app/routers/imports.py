import json

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.models import Finding, Test, User
from app.services.csv_import import (
    FINDING_FIELDS,
    TEST_FIELDS,
    build_import,
    decode_csv,
)

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("/fields")
def import_fields(_: User = Depends(require_admin)):
    """Target fields a CSV column can be mapped to."""
    return {"test_fields": TEST_FIELDS, "finding_fields": FINDING_FIELDS}


@router.post("/preview")
async def preview(file: UploadFile, _: User = Depends(require_admin)):
    """Return CSV headers and the first rows so the user can map columns."""
    raw = await file.read()
    rows, headers = decode_csv(raw)
    if not headers:
        raise HTTPException(status_code=422, detail="No columns found in CSV")
    return {
        "headers": headers,
        "sample": rows[:5],
        "row_count": len(rows),
    }


@router.post("/commit")
async def commit(
    file: UploadFile,
    mapping: str = Form(...),  # JSON: {csv_column: target_field}
    mode: str = Form("new"),  # "new" = create test; "append:<test_id>" = add to existing
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        mapping_dict = json.loads(mapping)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="mapping must be valid JSON")

    raw = await file.read()
    rows, headers = decode_csv(raw)
    if not rows:
        raise HTTPException(status_code=422, detail="CSV has no data rows")

    test_data, findings_data, issues = build_import(rows, mapping_dict)

    # Resolve target test
    if mode.startswith("append:"):
        test_id = int(mode.split(":", 1)[1])
        test = db.get(Test, test_id)
        if not test:
            raise HTTPException(status_code=404, detail="Target test not found")
    else:
        if not test_data.get("name"):
            test_data["name"] = file.filename or "Imported test"
        test = Test(**test_data, logged_by_user_id=user.id)
        db.add(test)
        db.flush()  # get test.id

    created = 0
    for fd in findings_data:
        # skip completely empty rows
        if not any(v for v in fd.values()):
            continue
        db.add(Finding(test_id=test.id, **fd))
        created += 1

    db.commit()
    db.refresh(test)

    return {
        "test_id": test.id,
        "test_name": test.name,
        "findings_created": created,
        "issue_count": len(issues),
        "issues": issues[:200],  # cap payload
    }
