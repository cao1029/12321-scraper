"""
12321.cn complaint data scraper.
Runs on GitHub Actions every hour 8:00-22:00 China time.
Fetches complaint count, appends to CSV, generates unified HTML report.
"""
import re
import csv
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

# ============ Config ============
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "scraped_data.csv"
TEMPLATE_FILE = BASE_DIR / "template_unified.html"
REPORT_FILE = BASE_DIR / "reports" / "report.html"
TARGET_URL = "https://www.12321.cn/"

# China timezone
CHINA_TZ = timezone(timedelta(hours=8))


def fetch_count():
    """Fetch complaint count from 12321.cn."""
    print(f"[{datetime.now(CHINA_TZ):%Y-%m-%d %H:%M:%S}] Fetching {TARGET_URL}")
    resp = requests.get(TARGET_URL, timeout=30)
    resp.raise_for_status()
    html = resp.text

    match = re.search(r'<span\s+class="count">([\d,]+)</span>', html)
    if not match:
        raise RuntimeError("Failed to extract complaint count from page")

    count = int(match.group(1).replace(",", ""))
    print(f"Extracted count: {count}")
    return count


def save_to_csv(dt_str, count):
    """Append data row to CSV."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = DATA_FILE.exists()
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["datetime", "count"])
        writer.writerow([dt_str, count])
    print(f"Data saved: {dt_str}, {count}")


def read_csv():
    """Read all rows from CSV, return list of dicts."""
    if not DATA_FILE.exists():
        return []
    rows = []
    with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "datetime": row["datetime"],
                "count": int(row["count"]),
            })
    return rows


def generate_report(rows, latest_count, now_cn):
    """Generate unified HTML report from template."""
    date_str = now_cn.strftime("%Y-%m-%d")
    current_month = now_cn.strftime("%Y-%m")
    update_time = now_cn.strftime("%Y-%m-%d %H:%M:%S")

    # Parse rows with date/time fields
    parsed = []
    for r in rows:
        dt = r["datetime"]
        parsed.append({
            "datetime": dt,
            "date": dt[:10],
            "time": dt[11:],
            "count": r["count"],
        })

    # Today's rows
    today_rows = [r for r in parsed if r["date"] == date_str]

    # Daily totals: last entry per day
    by_date = {}
    for r in parsed:
        by_date[r["date"]] = r  # later entries overwrite earlier ones
    daily_totals = sorted(by_date.values(), key=lambda x: x["date"])

    # Current month totals
    monthly_totals = [r for r in daily_totals if r["date"].startswith(current_month)]

    # ---- Daily chart data ----
    daily_labels = [f"'{r['datetime'][11:16]}'" for r in today_rows]
    daily_counts = [r["count"] for r in today_rows]
    daily_labels_js = ", ".join(daily_labels) if daily_labels else ""
    daily_counts_js = ", ".join(str(c) for c in daily_counts) if daily_counts else ""

    daily_max = 100
    if daily_counts:
        daily_max = int(max(daily_counts) * 1.1) + 1
    daily_ymin = int(min(daily_counts) * 0.5) if daily_counts else 0

    daily_table_rows = "\n".join(
        f'<tr><td>{r["time"]}</td><td>{r["count"]:,}</td></tr>'
        for r in today_rows
    ) or '<tr><td colspan="2" class="empty">No data yet</td></tr>'

    today_points = len(today_rows)

    # ---- Monthly chart data ----
    month_labels = [f"'{r['date'][8:10]}'" for r in monthly_totals]
    month_counts = [r["count"] for r in monthly_totals]
    month_labels_js = ", ".join(month_labels) if month_labels else ""
    month_counts_js = ", ".join(str(c) for c in month_counts) if month_counts else ""

    month_max = 100
    month_avg = 0
    month_days = len(monthly_totals)
    if month_counts:
        month_max = int(max(month_counts) * 1.15) + 1
        month_avg = int(sum(month_counts) / len(month_counts))
    month_ymin = int(min(month_counts) * 0.5) if month_counts else 0

    month_table_rows = "\n".join(
        f'<tr><td>{r["date"]}</td><td>{r["count"]:,}</td><td>{r["time"]}</td></tr>'
        for r in monthly_totals
    ) or '<tr><td colspan="3" class="empty">No data yet</td></tr>'

    # ---- Read template and fill ----
    if not TEMPLATE_FILE.exists():
        raise RuntimeError(f"Template not found: {TEMPLATE_FILE}")

    template = TEMPLATE_FILE.read_text(encoding="utf-8")

    report = template.replace("{{UPDATE_TIME}}", update_time)
    report = report.replace("{{DATE_STR}}", date_str)
    report = report.replace("{{CURRENT_MONTH}}", current_month)
    report = report.replace("{{LATEST_COUNT}}", f"{latest_count:,}")
    report = report.replace("{{TODAY_POINTS}}", str(today_points))
    report = report.replace("{{MONTH_DAYS}}", str(month_days))
    report = report.replace("{{MONTH_AVG}}", f"{month_avg:,}")
    report = report.replace("{{DAILY_LABELS}}", daily_labels_js)
    report = report.replace("{{DAILY_COUNTS}}", daily_counts_js)
    report = report.replace("{{DAILY_YMIN}}", str(daily_ymin))
    report = report.replace("{{DAILY_YMAX}}", str(daily_max))
    report = report.replace("{{DAILY_TABLE_ROWS}}", daily_table_rows)
    report = report.replace("{{MONTHLY_LABELS}}", month_labels_js)
    report = report.replace("{{MONTHLY_COUNTS}}", month_counts_js)
    report = report.replace("{{MONTHLY_YMIN}}", str(month_ymin))
    report = report.replace("{{MONTHLY_YMAX}}", str(month_max))
    report = report.replace("{{MONTHLY_TABLE_ROWS}}", month_table_rows)

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"Report generated: {REPORT_FILE}")


def main():
    now_cn = datetime.now(CHINA_TZ)
    dt_str = now_cn.strftime("%Y-%m-%d %H:%M:%S")
    hour_cn = now_cn.hour

    # Only run between 8:00 and 24:00 China time (inclusive)
    if hour_cn < 8:
        print(f"[{dt_str}] Outside running window (8:00-24:00), skipping. Current hour: {hour_cn}")
        return
    print(f"[{dt_str}] Within running window (8:00-24:00), starting scrape...")

    # 1. Fetch
    try:
        count = fetch_count()
    except Exception as e:
        print(f"ERROR fetching data: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Save to CSV
    save_to_csv(dt_str, count)

    # 3. Read all CSV data
    rows = read_csv()

    # 4. Generate report
    generate_report(rows, count, now_cn)

    print(f"[{dt_str}] Done! Complaint count: {count}")


if __name__ == "__main__":
    main()
