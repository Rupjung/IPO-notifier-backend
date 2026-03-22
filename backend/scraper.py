import requests
from bs4 import BeautifulSoup
import hashlib
from datetime import datetime

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

EXISTING_URL = "https://www.sharesansar.com/existing-issues"
UPCOMING_URL = "https://www.sharesansar.com/upcoming-issue"


def make_id(company: str, issue_type: str, open_date: str) -> str:
    """Generate a unique ID from company + type + open_date."""
    raw = f"{company}-{issue_type}-{open_date}".lower().replace(" ", "-")
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def parse_existing_issues(soup: BeautifulSoup, tab_id: str, issue_type: str) -> list:
    """Parse a specific tab table from /existing-issues page."""
    issues = []

    section = soup.find("div", {"id": tab_id})
    if not section:
        return issues

    table = section.find("table")
    if not table:
        return issues

    rows = table.find_all("tr")[1:]  # skip header row

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        company   = cols[0].get_text(strip=True)
        open_date = cols[1].get_text(strip=True)
        close_date= cols[2].get_text(strip=True)
        units     = cols[3].get_text(strip=True) if len(cols) > 3 else "N/A"

        if not company:
            continue

        issues.append({
            "id":         make_id(company, issue_type, open_date),
            "company":    company,
            "type":       issue_type,
            "open_date":  open_date,
            "close_date": close_date,
            "units":      units,
            "source":     "existing"
        })

    return issues


def parse_upcoming_issues(soup: BeautifulSoup) -> list:
    """Parse /upcoming-issue page."""
    issues = []

    table = soup.find("table")
    if not table:
        return issues

    rows = table.find_all("tr")[1:]

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        company    = cols[0].get_text(strip=True)
        issue_type = cols[1].get_text(strip=True).upper()
        open_date  = cols[2].get_text(strip=True)
        close_date = cols[3].get_text(strip=True)

        # Normalize type label
        if "FPO" in issue_type:
            issue_type = "FPO"
        elif "RIGHT" in issue_type:
            issue_type = "RIGHT"
        else:
            issue_type = "IPO"

        if not company:
            continue

        issues.append({
            "id":         make_id(company, issue_type, open_date),
            "company":    company,
            "type":       issue_type,
            "open_date":  open_date,
            "close_date": close_date,
            "units":      "N/A",
            "source":     "upcoming"
        })

    return issues


def scrape_all() -> dict:
    """Main scrape function. Returns all issues as a dict."""
    all_issues = []
    seen_ids = set()

    try:
        # --- Existing Issues ---
        res = requests.get(EXISTING_URL, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        for tab_id, issue_type in [
            ("ipo",        "IPO"),
            ("fpo",        "FPO"),
            ("rightshare", "RIGHT"),
        ]:
            for issue in parse_existing_issues(soup, tab_id, issue_type):
                if issue["id"] not in seen_ids:
                    seen_ids.add(issue["id"])
                    all_issues.append(issue)

    except Exception as e:
        print(f"[scraper] Error fetching existing issues: {e}")

    try:
        # --- Upcoming Issues ---
        res = requests.get(UPCOMING_URL, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        for issue in parse_upcoming_issues(soup):
            if issue["id"] not in seen_ids:
                seen_ids.add(issue["id"])
                all_issues.append(issue)

    except Exception as e:
        print(f"[scraper] Error fetching upcoming issues: {e}")

    return {
        "issues":     all_issues,
        "count":      len(all_issues),
        "scraped_at": datetime.utcnow().isoformat() + "Z"
    }