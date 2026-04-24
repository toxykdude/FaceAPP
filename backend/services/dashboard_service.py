"""
Dashboard service — SQL aggregation methods.
Extracts dashboard logic from route handlers for testability and reuse.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, List, Optional
from collections import defaultdict

from models.sale import SalesTransaction
from models.event import AccessEvent
from models.member import Member
from models.membership import Membership


class DashboardService:
    """Handles all dashboard data aggregation."""

    def __init__(self, db: Session):
        self.db = db

    def get_revenue_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=days)

        sales = self.db.query(SalesTransaction).filter(
            SalesTransaction.transaction_date >= period_start
        ).all()

        daily_revenue = defaultdict(float)
        for s in sales:
            key = s.transaction_date.strftime("%Y-%m-%d")
            daily_revenue[key] += float(s.amount)

        revenue_trend = []
        for i in range(days):
            d = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            revenue_trend.append({"date": d, "amount": daily_revenue.get(d, 0)})
        return revenue_trend

    def get_member_growth(self, months: int = 6) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        member_growth = []
        for i in range(months - 1, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            m_start = now.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)
            if i == 0:
                m_end = now
            else:
                nm = m + 1
                ny = y
                if nm > 12:
                    nm = 1
                    ny += 1
                m_end = m_start.replace(month=nm, year=ny)

            count = self.db.query(Member).filter(
                Member.created_at >= m_start,
                Member.created_at < m_end
            ).count()
            member_growth.append({"month": m_start.strftime("%b %Y"), "count": count})
        return member_growth

    def get_membership_distribution(self) -> List[Dict[str, Any]]:
        memberships = self.db.query(
            Membership.type, func.count(Membership.id)
        ).filter(
            Membership.status == "active"
        ).group_by(Membership.type).all()
        return [{"plan": name or "Unknown", "count": count} for name, count in memberships]

    def get_peak_hours(self) -> List[Dict[str, Any]]:
        all_events = self.db.query(AccessEvent).filter(
            AccessEvent.access_granted == True,
        ).all()

        hourly = defaultdict(int)
        for e in all_events:
            hour = e.timestamp.hour if e.timestamp else 0
            hourly[hour] += 1

        peak_hours = []
        for h in range(6, 23):
            label = f"{h % 12 or 12}{'AM' if h < 12 else 'PM'}"
            peak_hours.append({"hour": h, "label": label, "checkins": hourly.get(h, 0)})
        return peak_hours

    def get_checkin_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=days)

        events = self.db.query(AccessEvent).filter(
            AccessEvent.access_granted == True,
            AccessEvent.timestamp >= period_start
        ).all()

        daily_checkins = defaultdict(int)
        for e in events:
            key = e.timestamp.strftime("%Y-%m-%d")
            daily_checkins[key] += 1

        checkin_trend = []
        for i in range(days):
            d = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            checkin_trend.append({"date": d, "count": daily_checkins.get(d, 0)})
        return checkin_trend

    def get_new_signups(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (month_start - timedelta(days=1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        new_this_month = self.db.query(Member).filter(Member.created_at >= month_start).count()
        new_last_month = self.db.query(Member).filter(
            Member.created_at >= last_month_start,
            Member.created_at < month_start
        ).count()

        signup_change = ((new_this_month - new_last_month) / new_last_month * 100) if new_last_month > 0 else 0

        return {
            "this_month": new_this_month,
            "last_month": new_last_month,
            "change_pct": round(signup_change, 1),
        }

    def get_active_vs_expired(self) -> Dict[str, int]:
        active_count = self.db.query(Membership).filter(Membership.status == "active").count()
        expired_count = self.db.query(Membership).filter(Membership.status == "expired").count()
        return {"active": active_count, "expired": expired_count}

    def get_checkins_today(self) -> int:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.db.query(AccessEvent).filter(
            AccessEvent.access_granted == True,
            AccessEvent.timestamp >= today_start
        ).count()

    def get_checkins_week(self) -> int:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        return self.db.query(AccessEvent).filter(
            AccessEvent.access_granted == True,
            AccessEvent.timestamp >= week_start
        ).count()

    def get_revenue_change_pct(self, days: int = 30) -> float:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (month_start - timedelta(days=1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        sales = self.db.query(SalesTransaction).filter(
            SalesTransaction.transaction_date >= now - timedelta(days=days)
        ).all()

        rev_this_month = sum(float(s.amount) for s in sales if s.transaction_date >= month_start)
        rev_last_month_sales = self.db.query(SalesTransaction).filter(
            SalesTransaction.transaction_date >= last_month_start,
            SalesTransaction.transaction_date < month_start
        ).all()
        rev_last_month = sum(float(s.amount) for s in rev_last_month_sales)
        revenue_change = ((rev_this_month - rev_last_month) / rev_last_month * 100) if rev_last_month > 0 else 0
        return round(revenue_change, 1)

    def get_dashboard(self, days: int = 30) -> Dict[str, Any]:
        return {
            "revenue_trend": self.get_revenue_trend(days),
            "member_growth": self.get_member_growth(),
            "membership_distribution": self.get_membership_distribution(),
            "peak_hours": self.get_peak_hours(),
            "checkin_trend": self.get_checkin_trend(days),
            "new_signups": self.get_new_signups(),
            "active_vs_expired": self.get_active_vs_expired(),
            "checkins_today": self.get_checkins_today(),
            "checkins_week": self.get_checkins_week(),
            "revenue_change_pct": self.get_revenue_change_pct(days),
        }
