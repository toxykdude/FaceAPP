"""
Scheduled email reports for admin users.
Sends a summary every 2 hours with sales, new members, and recognized expired members.
"""
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from decimal import Decimal

from api.deps import get_db, get_current_user
from models.user import User
from models.member import Member
from models.membership import Membership
from models.sale import SalesTransaction
from models.event import AccessEvent
from core.email import email_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports-email", tags=["Reports Email"])


def generate_report_html(
    sales_count: int,
    sales_total: Decimal,
    sales_by_method: dict,
    new_members: list,
    recognized_expired: list,
    recognized_active: list,
    hours: int = 2,
) -> str:
    """Generate HTML email report."""
    
    # Sales section
    sales_html = f"""
    <div style="background: #f8f9fa; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
        <h3 style="margin: 0 0 10px 0; color: #333;">💰 Sales (Last {hours}h)</h3>
        <p style="font-size: 24px; font-weight: bold; margin: 0; color: #4caf50;">${sales_total:,.0f} COP</p>
        <p style="color: #666; margin: 5px 0 0 0;">{sales_count} transactions</p>
        <ul style="margin: 10px 0 0 0; padding-left: 20px;">
            <li>Cash: ${sales_by_method.get("cash", 0):,.0f}</li>
            <li>Transfer: ${sales_by_method.get("transfer", 0):,.0f}</li>
        </ul>
    </div>"""
    
    # New members section
    if new_members:
        members_rows = "".join(f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m["name"]}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m["id_number"] or "-"}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m["created_at"]}</td>
            </tr>""" for m in new_members)
        members_html = f"""
        <div style="background: #f8f9fa; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 10px 0; color: #333;">👤 New Members ({len(new_members)})</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background: #e0e0e0;">
                    <th style="padding: 8px; text-align: left;">Name</th>
                    <th style="padding: 8px; text-align: left;">ID</th>
                    <th style="padding: 8px; text-align: left;">Registered</th>
                </tr>
                {members_rows}
            </table>
        </div>"""
    else:
        members_html = """<div style="background: #f8f9fa; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 10px 0; color: #333;">👤 New Members</h3>
            <p style="color: #666;">No new members in this period.</p>
        </div>"""
    
    # Recognized expired section
    if recognized_expired:
        expired_rows = "".join(f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m["name"]}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m["id_number"] or "-"}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; color: #f44336;">{m["expired_date"]}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m["last_seen"]}</td>
            </tr>""" for m in recognized_expired)
        expired_html = f"""
        <div style="background: #fff3e0; border-radius: 8px; padding: 16px; margin-bottom: 20px; border: 1px solid #ff9800;">
            <h3 style="margin: 0 0 10px 0; color: #e65100;">⚠️ Recognized with Expired Membership ({len(recognized_expired)})</h3>
            <p style="color: #666; margin: 0 0 10px 0;">These members were detected by camera but have expired memberships:</p>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background: #ffe0b2;">
                    <th style="padding: 8px; text-align: left;">Name</th>
                    <th style="padding: 8px; text-align: left;">ID</th>
                    <th style="padding: 8px; text-align: left;">Expired</th>
                    <th style="padding: 8px; text-align: left;">Last Seen</th>
                </tr>
                {expired_rows}
            </table>
        </div>"""
    else:
        expired_html = """<div style="background: #f8f9fa; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 10px 0; color: #333;">⚠️ Recognized with Expired Membership</h3>
            <p style="color: #666;">No expired members recognized in this period.</p>
        </div>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 24px; margin-bottom: 24px;">
        <h1 style="color: white; margin: 0;">PowerHouse Gym</h1>
        <p style="color: rgba(255,255,255,0.8); margin: 5px 0 0 0;">Report • {datetime.now(timezone.utc).strftime("%b %d, %Y %I:%M %p")}</p>
    </div>
    {sales_html}
    {members_html}
    {expired_html}
    <div style="text-align: center; color: #999; font-size: 12px; margin-top: 30px;">
        <p>PowerHouse Gym Membership System • Auto-generated report</p>
    </div>
</body>
</html>"""


def send_scheduled_report(db_session_factory):
    """Generate and send the 2-hour report to all admin users."""
    from core.database import SessionLocal
    
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        two_hours_ago = now - timedelta(hours=2)
        
        # 1. Sales in last 2 hours
        sales = db.query(SalesTransaction).filter(
            SalesTransaction.transaction_date >= two_hours_ago
        ).all()
        
        sales_count = len(sales)
        sales_total = sum(float(s.amount) for s in sales) if sales else 0
        sales_by_method = {}
        for s in sales:
            method = s.payment_method
            sales_by_method[method] = sales_by_method.get(method, 0) + float(s.amount)
        
        # 2. New members in last 2 hours
        new_members_q = db.query(Member).filter(
            Member.created_at >= two_hours_ago
        ).all()
        new_members = [{
            "name": f"{m.first_name} {m.last_name}",
            "id_number": m.id_number,
            "created_at": m.created_at.strftime("%I:%M %p") if m.created_at else "",
        } for m in new_members_q]
        
        # 3. Recognized members with expired membership (last 2 hours)
        recognized_expired = []
        events_with_member = db.query(AccessEvent).filter(
            AccessEvent.member_id.isnot(None),
            AccessEvent.timestamp >= two_hours_ago
        ).all()
        
        seen_member_ids = set()
        for evt in events_with_member:
            if str(evt.member_id) in seen_member_ids:
                continue
            seen_member_ids.add(str(evt.member_id))
            
            member = db.query(Member).filter(Member.id == evt.member_id).first()
            if not member:
                continue
            
            # Check for any expired membership
            expired_ms = db.query(Membership).filter(
                Membership.member_id == evt.member_id,
                Membership.status == "expired"
            ).order_by(Membership.end_date.desc()).first()
            
            if expired_ms:
                recognized_expired.append({
                    "name": f"{member.first_name} {member.last_name}",
                    "id_number": member.id_number,
                    "expired_date": expired_ms.end_date.strftime("%b %d, %Y") if expired_ms.end_date else "N/A",
                    "last_seen": evt.timestamp.strftime("%I:%M %p") if evt.timestamp else "",
                })
        
        # 4. Recognized active members (for info)
        recognized_active = []
        active_member_ids = set()
        for evt in events_with_member:
            mid = str(evt.member_id)
            if mid in active_member_ids or mid in seen_member_ids:
                # Only add if not already in expired list
                if mid in seen_member_ids:
                    continue
            if mid in active_member_ids:
                continue
            
            member = db.query(Member).filter(Member.id == evt.member_id).first()
            if not member:
                continue
            
            active_ms = db.query(Membership).filter(
                Membership.member_id == evt.member_id,
                Membership.status == "active"
            ).first()
            
            if active_ms:
                active_member_ids.add(mid)
                recognized_active.append({
                    "member_id": mid,
                    "name": f"{member.first_name} {member.last_name}",
                })
        
        # Generate email
        html = generate_report_html(
            sales_count=sales_count,
            sales_total=Decimal(str(sales_total)),
            sales_by_method=sales_by_method,
            new_members=new_members,
            recognized_expired=recognized_expired,
            recognized_active=recognized_active,
        )
        
        # Send to all admin users
        admin_users = db.query(User).filter(User.role == "admin").all()
        for admin in admin_users:
            if admin.email:
                email_service._send_email(
                    to=admin.email,
                    subject=f"PowerHouse Gym Report - {now.strftime("%I:%M %p")} - {sales_count} sales, {len(new_members)} new members",
                    body=f"PowerHouse Gym Report: {sales_count} sales (${sales_total:,.0f}), {len(new_members)} new members, {len(recognized_expired)} expired members recognized.",
                    html=html,
                )
                logger.info(f"Report sent to {admin.email}")
        
        logger.info(f"Scheduled report complete: {sales_count} sales, {len(new_members)} new members, {len(recognized_expired)} expired recognized")
        
    except Exception as e:
        logger.error(f"Failed to send scheduled report: {e}", exc_info=True)
    finally:
        db.close()


# --- Manual trigger endpoint ---

@router.post("/send-now")
def send_report_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger the email report."""
    from core.database import SessionLocal
    send_scheduled_report(SessionLocal)
    return {"message": "Report sent successfully"}
