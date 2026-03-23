import re
import time
import requests
import hashlib
from datetime import datetime, timezone

EXISTING_URL = "https://www.sharesansar.com/existing-issues"

# ShareSansar blocks length >= 100. Safe max = 50.
# Use 20 per page on Render free tier to stay within memory limits.
PAGE_SIZE  = 20
PAGE_DELAY = 1  # seconds between pages — keeps memory pressure low

# Only fetch what we need for notifications:
# IPO=1, FPO=2, Rights=3, IPO-Local=5
ISSUE_TYPES = [
    {"type_id": 1, "label": "IPO"},
    {"type_id": 2, "label": "FPO"},
    {"type_id": 3, "label": "RIGHT"},
    {"type_id": 5, "label": "IPO"},
]

# Cap total records per type to avoid memory overload on free tier
# 265 IPO + 23 FPO + 317 Rights = ~600 total records
# At ~1KB per record that's fine but pagination overhead adds up
MAX_RECORDS_PER_TYPE = 300

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":           "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer":          EXISTING_URL,
}


def strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", str(text)).strip()


def make_id(company: str, issue_type: str, open_date: str) -> str:
    raw = f"{company}-{issue_type}-{open_date}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def fmt_units(val) -> str:
    try:
        return f"{int(float(val)):,}"
    except Exception:
        return str(val) if val else "N/A"


def status_label(status) -> str:
    try:
        s = int(status)
        if s in (-2, -1): return "coming_soon"
        elif s == 0:       return "open"
        else:              return "closed"
    except Exception:
        return "unknown"


def parse_record(row: dict, label: str) -> dict | None:
    try:
        co      = row.get("company", {})
        company = strip_html(co.get("companyname", ""))
        symbol  = strip_html(co.get("symbol", ""))
        if not company:
            return None

        open_date = (row.get("opening_date") or "").strip()

        return {
            "id":            make_id(company, label, open_date),
            "company":       company,
            "symbol":        symbol,
            "type":          label,
            "open_date":     open_date,
            "close_date":    (row.get("closing_date")  or "").strip(),
            "final_date":    (row.get("final_date")    or "").strip(),
            "listing_date":  (row.get("listing_date")  or "").strip(),
            "units":         fmt_units(row.get("total_units")),
            "issue_price":   str(row.get("issue_price") or "").strip(),
            "issue_manager": (row.get("issue_manager")  or "").strip(),
            "status":        status_label(row.get("status")),
            "source":        "existing",
        }
    except Exception as e:
        print(f"[scraper] Parse error: {e}")
        return None


def fetch_all_pages(type_id: int, label: str) -> list:
    """Paginate through all records using PAGE_SIZE=20."""
    all_issues = []
    start      = 0
    total      = None
    draw       = 1

    while True:
        try:
            res = requests.get(
                EXISTING_URL,
                params={
                    "type":   type_id,
                    "draw":   draw,
                    "start":  start,
                    "length": PAGE_SIZE,
                },
                headers=HEADERS,
                timeout=15,
            )
            res.raise_for_status()
            data = res.json()

        except Exception as e:
            print(f"[scraper] Request error type={type_id} start={start}: {e}")
            break

        if total is None:
            total = data.get("recordsTotal", 0)
            print(f"[scraper] type={type_id} ({label}): {total} total records")

        records = data.get("data", [])
        if not records:
            break

        for row in records:
            issue = parse_record(row, label)
            if issue:
                all_issues.append(issue)

        start += len(records)
        draw  += 1

        print(f"[scraper]   fetched {start}/{total}")

        # Stop conditions
        if start >= total:
            break
        if start >= MAX_RECORDS_PER_TYPE:
            print(f"[scraper]   hit MAX_RECORDS_PER_TYPE cap ({MAX_RECORDS_PER_TYPE})")
            break

        # Polite delay between pages
        time.sleep(PAGE_DELAY)

    return all_issues


def scrape_all() -> dict:
    all_issues = []
    seen_ids   = set()

    for i, t in enumerate(ISSUE_TYPES):
        if i > 0:
            time.sleep(PAGE_DELAY)

        for issue in fetch_all_pages(t["type_id"], t["label"]):
            if issue["id"] not in seen_ids:
                seen_ids.add(issue["id"])
                all_issues.append(issue)

    print(f"[scraper] Done. Total unique issues: {len(all_issues)}")

    return {
        "issues":     all_issues,
        "count":      len(all_issues),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import json
    result = scrape_all()
    print()
    print(f"Total: {result['count']}")
    for issue in result["issues"][:5]:
        print(f"  [{issue['type']}] ({issue['status'].upper()}) "
              f"{issue['company']} ({issue['symbol']})")
        print(f"        Open: {issue['open_date'] or 'TBA'}  "
              f"Close: {issue['close_date'] or 'TBA'}")