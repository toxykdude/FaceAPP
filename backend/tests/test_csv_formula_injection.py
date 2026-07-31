"""
CSV formula-injection tests (WS-10c, CWE-1236).

sanitize_csv_cell neutralizes spreadsheet formula injection: a cell beginning
with a formula metacharacter (= + - @ \\t \\r) is prefixed with a single quote
so spreadsheets treat it as text. Covers the helper (used by both the member
and sales CSV exports) plus an end-to-end sales export with a formula payload.
"""

import csv
import io
import uuid
from datetime import datetime, timezone

from core.csv_safety import sanitize_csv_cell


class TestSanitizeCsvCell:
    def test_formula_metacharacters_prefixed(self):
        for ch in ("=", "+", "-", "@", "\t", "\r"):
            assert sanitize_csv_cell(ch + "evil") == "'" + ch + "evil"

    def test_normal_values_unchanged(self):
        assert sanitize_csv_cell("John") == "John"
        assert sanitize_csv_cell("100") == "100"
        assert sanitize_csv_cell("a=b") == "a=b"  # '=' is not the FIRST char
        assert sanitize_csv_cell("member@host") == "member@host"

    def test_none_and_non_string(self):
        assert sanitize_csv_cell(None) == ""
        assert sanitize_csv_cell(42) == "42"
        assert sanitize_csv_cell(3.5) == "3.5"


class TestSalesExportFormulaInjection:
    def test_formula_cells_neutralized_in_export(
        self, client, auth_headers, db_session
    ):
        from models.member import Member
        from models.sale import SalesTransaction

        # Member whose name is a formula payload.
        member = Member(
            first_name='=HYPERLINK("http://evil","x")',
            last_name="Tester",
            email=f"csv-{uuid.uuid4().hex[:8]}@example.com",
            phone="555-0100",
            status="active",
        )
        db_session.add(member)
        db_session.flush()
        tx = SalesTransaction(
            member_id=member.id,
            amount=100,
            payment_method="cash",
            invoice_number="=1+1",
            transaction_date=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            notes="@cmd",
        )
        db_session.add(tx)
        db_session.commit()

        resp = client.get(
            "/api/sales/report/export",
            headers=auth_headers,
            params={"start_date": "2026-01-10", "end_date": "2026-01-20"},
        )
        assert resp.status_code == 200, resp.text

        # Drop the UTF-8 BOM before parsing.
        data = resp.content.decode("utf-8").lstrip("\ufeff")
        rows = list(csv.reader(io.StringIO(data)))
        assert len(rows) >= 2  # header + data row

        # Security property: NO cell in the export may start with a spreadsheet
        # formula metacharacter. Sanitized cells start with a single quote
        # instead (e.g. "'=HYPERLINK..."), so a raw "=..." / "@..." would fail.
        formula_chars = ("=", "+", "-", "@", "\t", "\r")
        for row in rows:
            for cell in row:
                assert not cell.startswith(formula_chars), cell

        # And confirm the formula payload actually landed (neutralized): the
        # data row contains the HYPERLINK payload, now single-quote-prefixed.
        data_row = rows[-1]
        assert any("'=HYPERLINK" in c for c in data_row), data_row
