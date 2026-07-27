#!/usr/bin/env python3
"""Live-server runtime harness for PR1 (custom-report-date-range spec).
Tracked support artifact (not /tmp). Spawns a REAL uvicorn against the real
PostgreSQL DB (no TestClient) and proves over HTTP: reversed range -> 422 on
both endpoints; valid range -> 200 with dashboard sum(revenue_trend) ==
summary.total_revenue and out-of-window rows excluded. Cleans up seeded rows
and the server process in a ``finally`` block regardless of PASS/FAIL.

Run: cd backend && PYTHONPATH=/root/faceapp/backend \
    /root/faceapp/.venv/bin/python tests/support/runtime_harness.py
"""
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import settings  # noqa: E402
from core.security import create_access_token  # noqa: E402
from models.member import Member  # noqa: E402
from models.sale import SalesTransaction  # noqa: E402
from models.user import User  # noqa: E402

HOST, PORT = "127.0.0.1", int(os.environ.get("PR1_HARNESS_PORT", "8321"))
BASE = f"http://{HOST}:{PORT}/api"
# Deterministic far-future window: Colombia 2099-06-10..20 -> UTC half-open
# [2099-06-10 05:00, 2099-06-21 05:00)
WINDOW_START, WINDOW_END = "2099-06-10", "2099-06-20"

def seed(session) -> Dict[str, Any]:
    member = Member(first_name="Harness", last_name="Runner",
                     email=f"harness-{uuid.uuid4().hex[:8]}@example.com",
                     phone="555-0100", status="active")
    session.add(member)
    session.flush()
    suffix = uuid.uuid4().hex[:6]
    rows = [
        (datetime(2099, 6, 10, 12), 100, "cash"),  # in-window
        (datetime(2099, 6, 15, 12), 250, "card"),  # in-window
        (datetime(2099, 6, 9, 12), 999, "cash"),   # before window
        (datetime(2099, 6, 21, 5), 888, "card"),   # half-open end -> excluded
    ]
    txs: List[SalesTransaction] = []
    for i, (dt, amount, method) in enumerate(rows):
        tx = SalesTransaction(member_id=member.id, amount=amount, payment_method=method,
                               invoice_number=f"INV-HARNESS-{i}-{suffix}", transaction_date=dt)
        session.add(tx)
        txs.append(tx)
    session.commit()
    return {"member": member, "txs": txs}

def cleanup(session, seeded: Dict[str, Any]) -> None:
    for tx in seeded.get("txs", []):
        session.query(SalesTransaction).filter(SalesTransaction.id == tx.id).delete()
    if seeded.get("member") is not None:
        session.query(Member).filter(Member.id == seeded["member"].id).delete()
    session.commit()

def wait_for_server(timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/health", timeout=1.0).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False

def main() -> int:
    engine = create_engine(settings.DATABASE_URL)
    session = sessionmaker(bind=engine)()
    seeded: Dict[str, Any] = {}
    proc = None
    try:
        seeded = seed(session)
        user = session.query(User).filter(User.username == "admin").first()
        if user is None:
            raise RuntimeError("No admin user in database; seed admin first.")
        headers = {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}

        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", HOST, "--port", str(PORT)],
            cwd=backend_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not wait_for_server():
            raise RuntimeError(f"uvicorn did not become ready on {HOST}:{PORT}")

        results: List[str] = []
        ok = True

        def check(name: str, cond: bool, detail: str) -> None:
            nonlocal ok
            results.append(f"[{'OK ' if cond else 'FAIL'}] {name}: {detail}")
            ok = ok and cond

        def get(path: str, params: dict) -> httpx.Response:
            return httpx.get(f"{BASE}{path}", params=params, headers=headers, timeout=5.0)

        reversed_params = {"start_date": WINDOW_END, "end_date": WINDOW_START}
        valid_params = {"start_date": WINDOW_START, "end_date": WINDOW_END}
        r = get("/sales/report/summary", reversed_params)
        check("summary reversed -> 422", r.status_code == 422, f"status={r.status_code}")
        r = get("/sales/dashboard", reversed_params)
        check("dashboard reversed -> 422", r.status_code == 422, f"status={r.status_code}")
        r = get("/sales/report/summary", valid_params)
        summ = r.json() if r.status_code == 200 else {}
        check("summary valid -> 200", r.status_code == 200, f"status={r.status_code}")
        check("summary totals (out-of-window excluded)",
              float(summ.get("total_revenue", -1)) == 350.0 and summ.get("total_transactions") == 2,
              f"total_revenue={summ.get('total_revenue')} total_transactions={summ.get('total_transactions')}")
        r = get("/sales/dashboard", valid_params)
        dash = r.json() if r.status_code == 200 else {}
        check("dashboard valid -> 200", r.status_code == 200, f"status={r.status_code}")
        dash_total = round(sum(p.get("amount", 0) for p in dash.get("revenue_trend", [])), 2)
        check("dashboard==summary totals agree (==350.0)",
              dash_total == round(float(summ.get("total_revenue", 0)), 2) == 350.0,
              f"sum(revenue_trend)={dash_total} summary={summ.get('total_revenue')}")

        print("=== PR1 runtime harness (live uvicorn + real PostgreSQL) ===")
        print("\n".join(results))
        print(f"RESULT: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        cleanup(session, seeded)
        session.close()
        engine.dispose()

if __name__ == "__main__":
    raise SystemExit(main())
