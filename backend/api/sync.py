"""
Sync API endpoints for client-server data synchronization.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from pydantic import BaseModel, Field

from api.deps import get_db, require_staff
from services.cv_notify import notify_cv_invalidation
from core.audit import log_action
from core.encryption import encrypt_string
from models.user import User, UserRole
from models.member import Member
from models.membership import Membership, MembershipPlan
from models.sale import SalesTransaction
from models.event import AccessEvent
from models.camera import Camera
from schemas.sync import SyncPullResponse, SyncPushResponse, SyncStatusResponse

router = APIRouter(prefix="/sync", tags=["Sync"])

SCHEMA_VERSION = 1

# Map table names to (model, change_tracking_column)
SYNC_TABLE_MAP = {
    "members": (Member, "updated_at"),
    "memberships": (Membership, "updated_at"),
    "sales_transactions": (SalesTransaction, "created_at"),
    "cameras": (Camera, "updated_at"),
    "access_events": (AccessEvent, "timestamp"),
    "users": (User, "updated_at"),
    "membership_plans": (MembershipPlan, "updated_at"),
}

# Allowed tables for push operations (more restricted than pull)
PUSH_ALLOWED_TABLES = {
    "members": Member,
    "memberships": Membership,
    "sales_transactions": SalesTransaction,
    "cameras": Camera,
}

# table -> page permission required to read/write it via sync.
# None = ADMIN-ONLY (sensitive: password hashes, RTSP credentials, audit events).
SYNC_TABLE_PAGE = {
    "members": "members",
    "memberships": "memberships",
    "membership_plans": "memberships",
    "sales_transactions": "sales",
    "users": None,  # admin-only: contains password hashes
    "cameras": None,  # admin-only: contains RTSP credentials
    "access_events": None,  # admin-only
}


def _assert_table_allowed(current_user: User, table_name: str) -> None:
    """Enforce per-table RBAC on sync. Admins bypass. None = admin-only."""
    page = SYNC_TABLE_PAGE.get(table_name)
    if current_user.role.upper() == UserRole.ADMIN.value.upper():
        return
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sync of '{table_name}' requires admin",
        )
    perms = current_user.permissions or {}
    pages = perms.get("pages", [])
    if "all" not in pages and page not in pages:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to {page}",
        )


def _serialize_value(val):
    """Convert a SQLAlchemy value to JSON-serializable type."""
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    return val


def _model_to_dict(instance) -> dict:
    """Convert a SQLAlchemy model instance to a plain dict."""
    mapper = inspect(instance).mapper
    result = {}
    for column in mapper.columns:
        result[column.key] = _serialize_value(getattr(instance, column.key))
    return result


# ---- Request / Response schemas ----


class PullRequest(BaseModel):
    last_sync_at: str = Field(
        ..., description="ISO 8601 timestamp to fetch changes after"
    )
    tables: List[str] = Field(
        default_factory=list, description="Tables to sync (empty = all)"
    )


class PushOperation(BaseModel):
    table: str
    operation: str = Field(..., description="INSERT, UPDATE, or DELETE")
    data: dict = Field(default_factory=dict)
    id: Optional[str] = Field(None, description="Record ID for UPDATE/DELETE")
    client_updated_at: Optional[str] = Field(
        None, description="Client's updated_at for conflict detection"
    )


class PushRequest(BaseModel):
    operations: List[PushOperation] = Field(default_factory=list)


class OperationResult(BaseModel):
    table: str
    id: Optional[str] = None
    status: str  # "success" or "error"
    error: Optional[str] = None


# ---- Endpoints ----


@router.post("/pull", response_model=SyncPullResponse)
def sync_pull(
    req: PullRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Pull records changed since last_sync_at from requested tables.

    Returns all records from the requested tables where the change tracking
    column (updated_at, created_at, or timestamp) is greater than last_sync_at.
    """
    # Parse the timestamp
    try:
        last_sync = datetime.fromisoformat(req.last_sync_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid last_sync_at format: {e}",
        )

    # Determine which tables to sync
    tables = req.tables if req.tables else list(SYNC_TABLE_MAP.keys())

    # Validate table names
    for table_name in tables:
        if table_name not in SYNC_TABLE_MAP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown table: {table_name}. Valid tables: {list(SYNC_TABLE_MAP.keys())}",
            )

    # Enforce per-table authorization BEFORE reading any data. Fail fast with
    # 403 if any requested table is not permitted; never return partial data.
    for table_name in tables:
        _assert_table_allowed(current_user, table_name)

    response = {}
    now = datetime.now(timezone.utc)

    for table_name in tables:
        model, change_col = SYNC_TABLE_MAP[table_name]
        col = getattr(model, change_col)

        records = db.query(model).filter(col > last_sync).all()
        response[table_name] = [_model_to_dict(r) for r in records]

    response["sync_timestamp"] = now.isoformat()
    response["schema_version"] = SCHEMA_VERSION

    return response


@router.post("/push", response_model=SyncPushResponse)
async def sync_push(
    req: PushRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Push a batch of operations from the client to the server.

    Operations:
    - INSERT: Insert a new record (skips if ID already exists)
    - UPDATE: Update an existing record (only if server updated_at is older than client's)
    - DELETE: Delete a record by ID
    """
    results = []
    now = datetime.now(timezone.utc)

    # Enforce per-table authorization for EVERY op BEFORE processing any of
    # them. Fail fast with 403 if any op targets a table the caller may not
    # write; do not partially apply a batch that contains an unauthorized op.
    for op in req.operations:
        _assert_table_allowed(current_user, op.table)

    for op in req.operations:
        table_name = op.table
        operation = op.operation.upper()
        data = op.data or {}

        # Validate table
        if table_name not in PUSH_ALLOWED_TABLES:
            results.append(
                OperationResult(
                    table=table_name,
                    status="error",
                    error=f"Table '{table_name}' is not allowed for push operations",
                )
            )
            continue

        if operation not in ("INSERT", "UPDATE", "DELETE"):
            results.append(
                OperationResult(
                    table=table_name,
                    status="error",
                    error=f"Invalid operation: {operation}",
                )
            )
            continue

        # Financial records are immutable via sync: sales_transactions allows
        # INSERT only (business-logic.sales-{delete,update}-integrity, CWE-840).
        if table_name == "sales_transactions" and operation != "INSERT":
            results.append(
                OperationResult(
                    table=table_name,
                    id=str(op.id or data.get("id") or ""),
                    status="error",
                    error="sales_transactions are immutable via sync (INSERT only)",
                )
            )
            continue

        model = PUSH_ALLOWED_TABLES[table_name]

        try:
            if operation == "INSERT":
                record_id = data.get("id")
                if record_id:
                    # Check if record already exists
                    existing = db.query(model).filter(model.id == record_id).first()
                    if existing:
                        results.append(
                            OperationResult(
                                table=table_name,
                                id=str(record_id),
                                status="error",
                                error="Record already exists",
                            )
                        )
                        continue

                # Build new record, only setting columns that exist on the model
                mapper = inspect(model).mapper
                valid_columns = {c.key for c in mapper.columns}
                filtered_data = {k: v for k, v in data.items() if k in valid_columns}

                # sales_transactions INSERT: server-generate the invoice number
                # when absent and reject negative amounts (input-validation.
                # sales-insert-validation, CWE-20/840).
                if table_name == "sales_transactions":
                    if not filtered_data.get("invoice_number"):
                        filtered_data["invoice_number"] = (
                            f"SYNC-{now.strftime('%Y%m%d')}-"
                            f"{uuid.uuid4().hex[:8].upper()}"
                        )
                    amt = filtered_data.get("amount")
                    if amt is None or (
                        isinstance(amt, (int, float, Decimal)) and Decimal(str(amt)) < 0
                    ):
                        results.append(
                            OperationResult(
                                table=table_name,
                                status="error",
                                error="sales_transactions INSERT requires a non-negative amount",
                            )
                        )
                        continue

                # cameras: encrypt the RTSP URL at rest, consistent with the
                # direct camera API (cleartext-sensitive-data.camera-insert,
                # CWE-312). The cv_service reads via /cv/cameras which decrypts.
                if table_name == "cameras" and filtered_data.get("rtsp_url"):
                    filtered_data["rtsp_url"] = encrypt_string(
                        filtered_data["rtsp_url"]
                    )

                new_record = model(**filtered_data)
                db.add(new_record)
                db.commit()
                db.refresh(new_record)
                results.append(
                    OperationResult(
                        table=table_name, id=str(new_record.id), status="success"
                    )
                )

            elif operation == "UPDATE":
                record_id = op.id or data.get("id")
                if not record_id:
                    results.append(
                        OperationResult(
                            table=table_name,
                            status="error",
                            error="No record ID provided for UPDATE",
                        )
                    )
                    continue

                existing = db.query(model).filter(model.id == record_id).first()
                if not existing:
                    results.append(
                        OperationResult(
                            table=table_name,
                            id=str(record_id),
                            status="error",
                            error="Record not found",
                        )
                    )
                    continue

                # Conflict detection: compare updated_at if both exist
                if (
                    op.client_updated_at
                    and hasattr(existing, "updated_at")
                    and existing.updated_at
                ):
                    try:
                        client_time = datetime.fromisoformat(
                            op.client_updated_at.replace("Z", "+00:00")
                        )
                        if existing.updated_at > client_time:
                            results.append(
                                OperationResult(
                                    table=table_name,
                                    id=str(record_id),
                                    status="error",
                                    error="Server record is newer (conflict)",
                                )
                            )
                            continue
                    except ValueError:
                        pass  # If parsing fails, proceed with update

                # Apply updates
                mapper = inspect(model).mapper
                valid_columns = {c.key for c in mapper.columns}
                skip_columns = {"id", "created_at"}  # Never overwrite these
                filtered_data = {
                    k: v
                    for k, v in data.items()
                    if k in valid_columns and k not in skip_columns
                }

                for key, value in filtered_data.items():
                    # cameras: encrypt a new RTSP URL on update, consistent with
                    # the direct camera API (cleartext-sensitive-data.camera-update).
                    if table_name == "cameras" and key == "rtsp_url" and value:
                        value = encrypt_string(value)
                    setattr(existing, key, value)

                if hasattr(existing, "updated_at"):
                    existing.updated_at = now

                db.commit()
                db.refresh(existing)
                results.append(
                    OperationResult(
                        table=table_name, id=str(existing.id), status="success"
                    )
                )

            elif operation == "DELETE":
                record_id = op.id or data.get("id")
                if not record_id:
                    results.append(
                        OperationResult(
                            table=table_name,
                            status="error",
                            error="No record ID provided for DELETE",
                        )
                    )
                    continue

                existing = db.query(model).filter(model.id == record_id).first()
                if not existing:
                    results.append(
                        OperationResult(
                            table=table_name,
                            id=str(record_id),
                            status="error",
                            error="Record not found",
                        )
                    )
                    continue

                is_member_delete = table_name == "members"
                db.delete(existing)
                if is_member_delete:
                    # Audit the protected deletion atomically (log_action only
                    # flushes; the commit below persists delete + audit together).
                    log_action(
                        db,
                        action="member_delete",
                        resource_type="member",
                        resource_id=str(record_id),
                        user_id=str(current_user.id),
                        username=current_user.username,
                        details={"via": "sync"},
                    )
                db.commit()
                if is_member_delete:
                    # Drop the member's facial template from the CV service cache
                    # (stale-resource.member-delete-audit-invalidation, CWE-672).
                    # notify_cv_invalidation swallows its own errors, so this is
                    # safe to await post-commit without breaking the response.
                    await notify_cv_invalidation(str(record_id))
                results.append(
                    OperationResult(
                        table=table_name, id=str(record_id), status="success"
                    )
                )

        except Exception as e:
            db.rollback()
            results.append(
                OperationResult(
                    table=table_name,
                    id=str(op.id) if op.id else str(data.get("id", "")),
                    status="error",
                    error=str(e),
                )
            )

    return {
        "results": [r.model_dump() for r in results],
        "sync_timestamp": now.isoformat(),
    }


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Get server sync metadata: current time, schema version, and table stats.
    """
    from sqlalchemy import func

    now = datetime.now(timezone.utc)
    tables_info = {}

    for table_name, (model, change_col) in SYNC_TABLE_MAP.items():
        col = getattr(model, change_col)
        count = db.query(func.count(model.id)).scalar()
        last_updated_row = db.query(col).order_by(col.desc()).first()
        last_updated = last_updated_row[0] if last_updated_row else None

        tables_info[table_name] = {
            "count": count,
            "last_updated": _serialize_value(last_updated),
        }

    return {
        "server_time": now.isoformat(),
        "schema_version": SCHEMA_VERSION,
        "tables": tables_info,
    }
