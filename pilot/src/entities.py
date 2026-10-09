"""Business-entity vs individual detection (phase 2 personal-data rule). Conservative: when unsure, treat as individual."""
from __future__ import annotations
import re

ENTITY = re.compile(r"\b(LLC|L\.L\.C|LP|L\.P|LLP|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|PLLC|PC|PA|TRUST|TRUSTEE|ISD|DISTRICT|"
                    r"CITY|COUNTY|STATE|UNIVERSITY|COLLEGE|SCHOOL|CHURCH|MINISTR\w*|FOUNDATION|AUTHORITY|ASSOCIATION|ASSOC|PARTNERS?|"
                    r"PARTNERSHIP|HOLDINGS?|PROPERTIES|REALTY|DEV|DEVELOPMENT|DEVELOPERS|BUILDERS?|CONSTRUCTION|GROUP|CAPITAL|VENTURES?|"
                    r"INVESTMENTS?|ENTERPRISES?|SERVICES|ENGINEERING|ENGINEERS|ARCHITECTS?|ARCHITECTURE|DESIGN|STUDIO|HOUSING|APARTMENTS|"
                    r"HOSPITAL|BANK|FUND|REIT|OWNERS|COMMUNITY|SOCIETY|COUNCIL|DEPARTMENT|DEPT|AUSTIN|TEXAS|TX|US|USA)\b", re.I)
NAME_LIKE = re.compile(r"^[A-Za-z'.\-]+(?:,?\s+[A-Za-z'.\-]+){1,3}$")


def is_entity(name: str | None) -> bool:
    if not name or not name.strip():
        return False
    n = name.strip()
    if ENTITY.search(n):
        return True
    # two to four plain tokens with no entity keyword looks like a person ("John Smith", "Smith, John A")
    return not NAME_LIKE.match(n)


def clean_entity(name: str | None) -> tuple[str | None, bool]:
    """-> (entity name or None, individual flag). The name is dropped when it looks like a person."""
    if not name or not name.strip():
        return None, False
    return (name.strip(), False) if is_entity(name) else (None, True)


TAG = re.compile(r"[\s\(\[\*]*\bMAIN\b[\s\)\]\*]*", re.I)


def clean_org(name: str | None) -> str | None:
    """Strip permit-system tags such as '(MAIN)', '***MAIN***', '*MAIN*' from an organization name; None if nothing real is left."""
    if not name:
        return None
    n = re.sub(r"\s+", " ", TAG.sub(" ", name)).strip(" *-,")
    return n or None
