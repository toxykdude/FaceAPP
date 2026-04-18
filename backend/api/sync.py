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
from models.user import User
from models.member import Member
from models.membership import Membership, MembershipPlan
from models.sale import SalesTransaction
from models.event import AccessEvent
from models.camera import Camera

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
    last_sync_at: str = Field(..., description="ISO 8601 timestamp to fetch changes after")
    tables: List[str] = Field(default_factory=list, description="Tables to sync (empty = all)")


class PushOperation(BaseModel):
    table: str
    operation: str = Field(..., description="INSERT, UPDATE, or DELETE")
    data: dict = Field(default_factory=dict)
    id: Optional[str] = Field(None, description="Record ID for UPDATE/DELETE")
    client_updated_at: Optional[str] = Field(None, description="Client's updated_at for conflict detection")


class PushRequest(BaseModel):
    operations: List[PushOperation] = Field(default_factory=list)


class OperationResult(BaseModel):
    table: str
    id: Optional[str] = None
    status: str  # "success" or "error"
    error: Optional[str] = None


# ---- Endpoints ----

@router.post("/pull")
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
            detail=f"Invalid last_sync_at format: {e}"
        )

    # Determine which tables to sync
    tables = req.tables if req.tables else list(SYNC_TABLE_MAP.keys())

    # Validate table names
    for table_name in tables:
        if table_name not in SYNC_TABLE_MAP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown table: {table_name}. Valid tables: {list(SYNC_TABLE_MAP.keys())}"
            )

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


@router.post("/push")
def sync_push(
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

    for op in req.operations:
        table_name = op.table
        operation = op.operation.upper()
        data = op.data or {}

        # Validate table
        if table_name not in PUSH_ALLOWED_TABLES:
            results.append(OperationResult(
                table=table_name,
                status="error",
                error=f"Table '{table_name}' is not allowed for push operations"
            ))
            continue

        if operation not in ("INSERT", "UPDATE", "DELETE"):
            results.append(OperationResult(
                table=table_name,
                status="error",
                error=f"Invalid operation: {operation}"
            ))
            continue

        model = PUSH_ALLOWED_TABLES[table_name]

        try:
            if operation == "INSERT":
                record_id = data.get("id")
                if record_id:
                    # Check if record already exists
                    existing = db.query(model).filter(model.id == record_id).first()
                    if existing:
                        results.append(OperationResult(
                            table=table_name,
                            id=str(record_id),
                            status="error",
                            error="Record already exists"
                        ))
                        continue

                # Build new record, only setting columns that exist on the model
                mapper = inspect(model).mapper
                valid_columns = {c.key for c in mapper.columns}
                filtered_data = {k: v for k, v in data.items() if k in valid_columns}

                new_record = model(**filtered_data)
                db.add(new_record)
                db.commit()
                db.refresh(new_record)
                results.append(OperationResult(
                    table=table_name,
                    id=str(new_record.id),
                    status="success"
                ))

            elif operation == "UPDATE":
                record_id = op.id or data.get("id")
                if not record_id:
                    results.append(OperationResult(
                        table=table_name,
                        status="error",
                        error="No record ID provided for UPDATE"
                    ))
                    continue

                existing = db.query(model).filter(model.id == record_id).first()
                if not existing:
                    results.append(OperationResult(
                        table=table_name,
                        id=str(record_id),
                        status="error",
                        error="Record not found"
                    ))
                    continue

                # Conflict detection: compare updated_at if both exist
                if op.client_updated_at and hasattr(existing, "updated_at") and existing.updated_at:
                    try:
                        client_time = datetime.fromisoformat(op.client_updated_at.replace("Z", "+00:00"))
                        if existing.updated_at > client_time:
                            results.append(OperationResult(
                                table=table_name,
                                id=str(record_id),
                                status="error",
                                error="Server record is newer (conflict)"
                            ))
                            continue
                    except ValueError:
                        pass  # If parsing fails, proceed with update

                # Apply updates
                mapper = inspect(model).mapper
                valid_columns = {c.key for c in mapper.columns}
                skip_columns = {"id", "created_at"}  # Never overwrite these
                filtered_data = {k: v for k, v in data.items() if k in valid_columns and k not in skip_columns}

                for key, value in filtered_data.items():
                    setattr(existing, key, value)

                if hasattr(existing, "updated_at"):
                    existing.updated_at = now

                db.commit()
                db.refresh(existing)
                results.append(OperationResult(
                    table=table_name,
                    id=str(existing.id),
                    status="success"
                ))

            elif operation == "DELETE":
                record_id = op.id or data.get("id")
                if not record_id:
                    results.append(OperationResult(
                        table=table_name,
                        status="error",
                        error="No record ID provided for DELETE"
                    ))
                    continue

                existing = db.query(model).filter(model.id == record_id).first()
                if not existing:
                    results.append(OperationResult(
                        table=table_name,
                        id=str(record_id),
                        status="error",
                        error="Record not found"
                    ))
                    continue

                db.delete(existing)
                db.commit()
                results.append(OperationResult(
                    table=table_name,
                    id=str(record_id),
                    status="success"
                ))

        except Exception as e:
            db.rollback()
            results.append(OperationResult(
                table=table_name,
                id=str(op.id) if op.id else str(data.get("id", "")),
                status="error",
                error=str(e)
            ))

    return {
        "results": [r.model_dump() for r in results],
        "sync_timestamp": now.isoformat(),
    }


@router.get("/status")
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
