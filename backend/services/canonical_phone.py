"""
Canonical-phone helpers shared by the member portal.

Phone numbers in ``members.phone`` are free-form contact data (deliberately
NOT unique — see migrations ``5a4b3c2d1e0f`` / ``6b5c4d3e2f1a``): the same
Colombian mobile exists in the wild as ``3001112233``, ``+57 300 111 2233``
and ``573001112233``. Every path that must correlate a submitted phone with
stored members canonicalizes BOTH sides to ``57 + 10 digits`` and resolves
through SQL — extracted from ``api/portal_auth.py`` so the guest provisioning
path (webhook-renew, design D5) reuses the exact same semantics as member
login.

Ambiguity is a hard failure: legacy data contains duplicate rows for one
human, so a lookup that matches more than one member resolves to None —
callers must never receive a coin-flip member.
"""

import re

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from models.member import Member


def canonicalize_phone(phone: str) -> str:
    """Normalize a phone to its digit string, prefixing 57 for 10-digit
    Colombian mobiles (leading 3). Anything else is returned as bare digits
    — the caller decides whether that is acceptable (guest checkout does
    not: it requires the result to match ``57`` + 10 digits)."""
    digits = re.sub(r"[^0-9]", "", phone)
    if len(digits) == 10 and digits.startswith("3"):
        return f"57{digits}"
    return digits


def find_members_by_canonical_phone(db: Session, canonical_phone: str) -> list[Member]:
    """All members whose stored phone canonicalizes to ``canonical_phone``.

    The canonicalization happens in SQL (regexp_replace + concat) so the
    comparison runs against the stored representation, whatever its format.
    Returns up to two candidates — callers only need to distinguish 0, 1
    and ">1" (ambiguity).
    """
    digits = func.regexp_replace(Member.phone, "[^0-9]", "", "g")
    stored_canonical = case(
        (
            and_(func.length(digits) == 10, digits.like("3%")),
            func.concat("57", digits),
        ),
        else_=digits,
    )
    return db.query(Member).filter(stored_canonical == canonical_phone).limit(2).all()


def resolve_member_by_phone(db: Session, canonical_phone: str) -> Member | None:
    """Return a member only for one unambiguous canonical-phone match.

    None means either "no member with this phone" or "more than one member
    matches" — both must be handled by the caller, never guessed.
    """
    if not canonical_phone:
        return None
    candidates = find_members_by_canonical_phone(db, canonical_phone)
    return candidates[0] if len(candidates) == 1 else None
