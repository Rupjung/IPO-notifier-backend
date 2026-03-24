import re
import time
import requests
import hashlib
from datetime import datetime, timezone

EXISTING_URL = "https://www.sharesansar.com/existing-issues"

PAGE_SIZE  = 20
PAGE_DELAY = 1

ISSUE_TYPES = [
    {"type_id": 1, "label": "IPO"},
    {"type_id": 2, "label": "FPO"},
    {"type_id": 3, "label": "RIGHT"}
]

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


def make_id(company: str, issue_type: str, symbol: str = "") -> str:
    raw = f"{company}-{issue_type}-{symbol}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def fmt_units(val) -> str:
    try:
        return f"{int(float(val)):,}"
    except Exception:
        return str(val) if val else "N/A"


def get_status(status_val, opening_date: str = "", closing_date: str = "") -> str:
    """
    Determine true status.
    ShareSansar sometimes marks status=0 (open) but has no actual dates —
    those are still "Coming Soon" in reality.
    A record is only truly OPEN if:
      - status code is 0 AND
      - it has a real opening_date AND closing_date (not empty)
    """
    try:
        s = int(status_val)
        if s in (-2, -1):
            return "coming_soon"
        elif s == 0:
            # Only mark as open if actual dates exist
            if opening_date.strip() and closing_date.strip():
                return "open"
            else:
                return "coming_soon"
        else:
            return "closed"
    except Exception:
        return "unknown"


def parse_record(row: dict, label: str) -> dict | None:
    try:
        co      = row.get("company", {})
        company = strip_html(co.get("companyname", ""))
        symbol  = strip_html(co.get("symbol", ""))
        if not company:
            return None

        open_date  = (row.get("opening_date") or "").strip()
        close_date = (row.get("closing_date") or "").strip()
        status     = get_status(row.get("status"), open_date, close_date)

        return {
            "id":            make_id(company, label, symbol),
            "company":       company,
            "symbol":        symbol,
            "type":          label,
            "open_date":     open_date,
            "close_date":    close_date,
            "final_date":    (row.get("final_date")    or "").strip(),
            "listing_date":  (row.get("listing_date")  or "").strip(),
            "units":         fmt_units(row.get("total_units")),
            "issue_price":   str(row.get("issue_price") or "").strip(),
            "issue_manager": (row.get("issue_manager")  or "").strip(),
            "status":        status,
            "source":        "existing",
        }
    except Exception as e:
        print(f"[scraper] Parse error: {e}")
        return None


def fetch_relevant_pages(type_id: int, label: str) -> list:
    """
    Fetch pages until we stop seeing open/coming_soon records.
    
    ShareSansar returns records ordered by status:
    - coming_soon first (status=-2)
    - open next (status=0)  
    - closed last (status=1+)
    
    So we stop fetching as soon as a full page contains only closed records.
    This way we never load the hundreds of closed records that crash Render.
    """
    all_issues     = []
    start          = 0
    total          = None
    draw           = 1
    consecutive_closed_pages = 0

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
            print(f"[scraper] type={type_id} ({label}): {total} total records on ShareSansar")

        records = data.get("data", [])
        if not records:
            break

        # Check if this page has any relevant (non-closed) issues
        page_has_relevant = False
        for row in records:
            status = get_status(
                    row.get("status"),
                    (row.get("opening_date") or ""),
                    (row.get("closing_date") or ""),
                )
            if status in ("open", "coming_soon"):
                page_has_relevant = True
            issue = parse_record(row, label)
            if issue:
                all_issues.append(issue)

        start += len(records)
        draw  += 1
        print(f"[scraper]   fetched {start} records (kept {len(all_issues)} relevant)")

        # If this page had no open/coming_soon, increment counter
        if not page_has_relevant:
            consecutive_closed_pages += 1
        else:
            consecutive_closed_pages = 0

        # Stop after 2 consecutive pages of only closed records
        # No point fetching more closed records
        if consecutive_closed_pages >= 2:
            print(f"[scraper]   stopping early — only closed records remain")
            break

        if start >= total:
            break

        time.sleep(PAGE_DELAY)

    return all_issues


def scrape_all() -> dict:
    all_issues = []

    for i, t in enumerate(ISSUE_TYPES):
        if i > 0:
            time.sleep(PAGE_DELAY)
        all_issues.extend(fetch_relevant_pages(t["type_id"], t["label"]))

    # Sort: open first, then coming_soon, then closed
    status_order = {"open": 0, "coming_soon": 1, "closed": 2, "unknown": 3}
    all_issues.sort(key=lambda x: status_order.get(x["status"], 3))

    print(f"[scraper] Done. Total unique issues: {len(all_issues)}")
    open_count  = sum(1 for i in all_issues if i["status"] == "open")
    soon_count  = sum(1 for i in all_issues if i["status"] == "coming_soon")
    print(f"[scraper]   Open: {open_count}  Coming Soon: {soon_count}")

    return {
        "issues":     all_issues,
        "count":      len(all_issues),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    result = scrape_all()
    print()
    print(f"Total: {result['count']}")
    for issue in result["issues"][:10]:
        print(f"  [{issue['type']}] ({issue['status'].upper()}) "
              f"{issue['company']} ({issue['symbol']})")
        print(f"        Open: {issue['open_date'] or 'TBA'}  "
              f"Close: {issue['close_date'] or 'TBA'}")
        print()