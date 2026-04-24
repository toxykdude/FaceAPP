"""Tests for sales API endpoints."""
import pytest


def test_list_sales_unauthenticated(client):
    response = client.get("/api/sales")
    assert response.status_code == 401


def test_dashboard_authenticated(auth_client):
    response = auth_client.get("/api/sales/dashboard")
    assert response.status_code == 200


def test_report_summary_authenticated(auth_client):
    """Route should be reachable (not shadowed by /{transaction_id})."""
    response = auth_client.get("/api/sales/report/summary")
    assert response.status_code == 200
