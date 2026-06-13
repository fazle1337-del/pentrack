from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import Role
from app.models.models import (
    Finding,
    FindingAttachment,
    Test,
    TestAttachment,
    User,
)
from app.routers.findings import _can_access
from app.schemas.schemas import AttachmentOut
from app.services.storage import storage

router = APIRouter(tags=["attachments"])


# ---- Test attachments (admin only — tests are admin-managed) ----
@router.post("/tests/{test_id}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_test_attachment(
    test_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    if not db.get(Test, test_id):
        raise HTTPException(status_code=404, detail="Test not found")
    data = await file.read()
    storage_path = storage.save(file.filename or "upload", data)
    att = TestAttachment(
        test_id=test_id,
        filename=file.filename or "upload",
        storage_path=storage_path,
        uploaded_by=user.id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


@router.get("/tests/{test_id}/attachments", response_model=list[AttachmentOut])
def list_test_attachments(
    test_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return (
        db.query(TestAttachment).filter(TestAttachment.test_id == test_id).all()
    )


@router.get("/test-attachments/{attachment_id}/download")
def download_test_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    att = db.get(TestAttachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = storage.full_path(att.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from storage")
    return FileResponse(path, filename=att.filename)


# ---- Finding attachments (owner/team or admin) ----
@router.post(
    "/findings/{finding_id}/attachments", response_model=AttachmentOut, status_code=201
)
async def upload_finding_attachment(
    finding_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if not _can_access(user, finding):
        raise HTTPException(status_code=403, detail="Not authorised for this finding")
    data = await file.read()
    storage_path = storage.save(file.filename or "upload", data)
    att = FindingAttachment(
        finding_id=finding_id,
        filename=file.filename or "upload",
        storage_path=storage_path,
        uploaded_by=user.id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


@router.get("/findings/{finding_id}/attachments", response_model=list[AttachmentOut])
def list_finding_attachments(
    finding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if not _can_access(user, finding):
        raise HTTPException(status_code=403, detail="Not authorised for this finding")
    return (
        db.query(FindingAttachment)
        .filter(FindingAttachment.finding_id == finding_id)
        .all()
    )


@router.get("/finding-attachments/{attachment_id}/download")
def download_finding_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att = db.get(FindingAttachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    finding = db.get(Finding, att.finding_id)
    if not _can_access(user, finding):
        raise HTTPException(status_code=403, detail="Not authorised for this finding")
    path = storage.full_path(att.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from storage")
    return FileResponse(path, filename=att.filename)
