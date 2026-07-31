"""
Bulk member import/export endpoints.
"""

import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from sqlalchemy.orm import Session

from api.deps import get_db, require_page
from models.user import User
from models.member import Member
from core.audit import log_action
from schemas.import_export import ImportResponse

router = APIRouter(prefix="/members", tags=["Import/Export"])


@router.post("/import", response_model=ImportResponse)
async def import_members(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("reports")),
):
    """
    Import members from CSV file.

    CSV columns: first_name, last_name, email (optional), phone (optional)
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    contents = await file.read()
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))

    required_fields = {"first_name", "last_name"}
    if not required_fields.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns: {', '.join(required_fields)}",
        )

    created = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
        try:
            member = Member(
                first_name=row["first_name"].strip(),
                last_name=row["last_name"].strip(),
                email=row.get("email", "").strip() or None,
                phone=row.get("phone", "").strip() or None,
                status="active",
                consent_given_at=None,
            )
            db.add(member)
            created += 1
        except Exception as e:
            errors.append({"row": row_num, "error": str(e)})

    # Audit (atomic with the import — log_action flushes; the commit below
    # persists both the imported members and the audit row).
    log_action(
        db,
        action="import",
        resource_type="member",
        user_id=str(current_user.id),
        username=current_user.username,
        details={"created": created, "errors": len(errors)},
    )
    db.commit()

    return {"created": created, "errors": errors, "total_rows": created + len(errors)}


@router.get("/export")
def export_members(
    search: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("reports")),
):
    """
    Export members to CSV file.
    """
    query = db.query(Member)

    if search:
        query = query.filter(
            (Member.first_name.ilike(f"%{search}%"))
            | (Member.last_name.ilike(f"%{search}%"))
            | (Member.email.ilike(f"%{search}%"))
        )

    if status:
        query = query.filter(Member.status == status)

    members = query.order_by(Member.last_name, Member.first_name).all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "first_name",
            "last_name",
            "email",
            "phone",
            "status",
            "facial_data_enrolled",
            "created_at",
        ]
    )

    for m in members:
        writer.writerow(
            [
                m.first_name,
                m.last_name,
                m.email or "",
                m.phone or "",
                m.status,
                m.facial_data_enrolled,
                m.created_at.isoformat() if m.created_at else "",
            ]
        )

    # Audit
    log_action(
        db,
        action="export",
        resource_type="member",
        user_id=str(current_user.id),
        username=current_user.username,
        details={"count": len(members)},
    )
    db.commit()

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=members_export.csv"},
    )
