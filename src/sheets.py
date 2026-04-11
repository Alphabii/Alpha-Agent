from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from loguru import logger
from pathlib import Path

from src.config import settings


def _format_date(iso_date: str) -> str:
    """Convert ISO date to simple 'YYYY-MM-DD HH:MM' in France time (UTC+2)."""
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(iso_date)
        dt = dt.astimezone(ZoneInfo("Europe/Paris"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_date[:16].replace("T", " ")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_ID = "1kyI4pcGEhySmHSPAeiAcntR8AG32BmWwju0B10EZGKo"
CREDS_PATH = Path(__file__).parent.parent / settings.google_service_account_path


def _get_client():
    """Authenticate and return the gspread client."""
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_worksheet(name: str, headers: list[str]):
    """Get a worksheet by name, or create it with headers."""
    gc = _get_client()
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=1000, cols=len(headers))
        ws.update(values=[headers], range_name=f"A1:{chr(64 + len(headers))}1")
        logger.info(f"Created worksheet '{name}' with headers")
    return ws


def _col_letter(n: int) -> str:
    """Convert 1-based column number to letter(s): 1->A, 26->Z, 27->AA."""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _append_row(ws, row: list):
    """Append a row to the next empty line."""
    all_values = ws.col_values(1)
    next_row = len(all_values) + 1
    end_col = _col_letter(len(row))
    ws.update(values=[row], range_name=f"A{next_row}:{end_col}{next_row}")


JOB_FOUND_HEADERS = [
    "Date",
    "Platform",
    "Title",
    "Company",
    "Location",
    "Remote",
    "Contract Type",
    "Duration",
    "Daily Rate Min",
    "Daily Rate Max",
    "Skills Required",
    "Score",
    "Reasoning",
    "Matching Skills",
    "Concerns",
    "Status",
    "Language",
    "URL",
]

APPLICATION_HEADERS = [
    "Date",
    "Platform",
    "Title",
    "Company",
    "Location",
    "Remote",
    "Daily Rate Min",
    "Daily Rate Max",
    "Score",
    "Status",
    "Application Result",
    "External URL",
    "URL",
    "Proposal",
]


CONTRACT_DISPLAY = {
    "contractor": "Freelance",
    "permanent": "CDI",
    "fixed_term": "CDD",
    "internship": "Stage",
    "apprenticeship": "Alternance",
}


def _format_contract(contract_type: str) -> str:
    """Convert API contract values to display names."""
    parts = [c.strip() for c in contract_type.split(",")]
    display = [CONTRACT_DISPLAY.get(p, p.capitalize()) for p in parts if p]
    return ", ".join(display) if display else contract_type


def track_job_found(
    date: str,
    platform: str,
    title: str,
    company: str,
    location: str,
    remote: bool,
    contract_type: str,
    duration: str,
    daily_rate_min: int,
    daily_rate_max: int,
    skills: list[str],
    score: int,
    reasoning: str,
    matching_skills: list[str],
    concerns: list[str],
    status: str,
    language: str,
    url: str,
):
    """Append a scored job to the 'Job Offers Found' worksheet."""
    try:
        ws = _get_or_create_worksheet("Job Offers Found", JOB_FOUND_HEADERS)
        row = [
            _format_date(date),
            platform,
            title,
            company,
            location,
            "Yes" if remote else "No",
            _format_contract(contract_type),
            duration,
            daily_rate_min,
            daily_rate_max,
            ", ".join(skills),
            score,
            reasoning,
            ", ".join(matching_skills),
            ", ".join(concerns),
            status,
            language,
            url,
        ]
        _append_row(ws, row)
        logger.info(f"Tracked job in 'Job Offers Found': {title[:50]}")
    except Exception as e:
        logger.error(f"Failed to track job in sheet: {e}")


def build_dashboard():
    """Create/update a Dashboard sheet with summary stats and charts."""
    try:
        gc = _get_client()
        sh = gc.open_by_key(SHEET_ID)

        # Recreate sheet to clear old content and charts
        try:
            sh.del_worksheet(sh.worksheet("Dashboard"))
        except gspread.exceptions.WorksheetNotFound:
            pass
        ws = sh.add_worksheet(title="Dashboard", rows=40, cols=15)
        sid = ws.id

        # Ensure data sheets exist
        _get_or_create_worksheet("Job Offers Found", JOB_FOUND_HEADERS)
        _get_or_create_worksheet("Free-Work", APPLICATION_HEADERS)

        # Write labels + formulas
        rows = [
            ["DASHBOARD"],
            [],
            ["JOBS OVERVIEW"],
            ["Total Jobs", '=COUNTA(\'Job Offers Found\'!A:A)-1'],
            ["Qualified", '=COUNTIF(\'Job Offers Found\'!P:P,"qualified")'],
            ["Skipped", '=COUNTIF(\'Job Offers Found\'!P:P,"skipped")'],
            ["Avg Score", '=IFERROR(ROUND(AVERAGE(\'Job Offers Found\'!L2:L),1),0)'],
            [],
            ["APPLICATIONS"],
            ["Total", "=COUNTA('Free-Work'!A:A)-1"],
            ["Submitted", '=COUNTIF(\'Free-Work\'!J:J,"submitted")'],
            ["Failed", '=COUNTIF(\'Free-Work\'!J:J,"failed")'],
            ["Already Applied", '=COUNTIF(\'Free-Work\'!K:K,"already_applied")'],
            ["Success Rate", '=IFERROR(TEXT(B11/MAX(B10,1),"0%"),"0%")'],
            [],
            ["SCORE DISTRIBUTION"],
            ["Range", "Count"],
            ["0-29", '=COUNTIFS(\'Job Offers Found\'!L2:L,">=0",\'Job Offers Found\'!L2:L,"<30")'],
            ["30-49", '=COUNTIFS(\'Job Offers Found\'!L2:L,">=30",\'Job Offers Found\'!L2:L,"<50")'],
            ["50-69", '=COUNTIFS(\'Job Offers Found\'!L2:L,">=50",\'Job Offers Found\'!L2:L,"<70")'],
            ["70-84", '=COUNTIFS(\'Job Offers Found\'!L2:L,">=70",\'Job Offers Found\'!L2:L,"<85")'],
            ["85-100", '=COUNTIFS(\'Job Offers Found\'!L2:L,">=85",\'Job Offers Found\'!L2:L,"<=100")'],
            [],
            ["CONTRACT TYPES"],
            ["Type", "Count"],
            ["Freelance", '=COUNTIF(\'Job Offers Found\'!G:G,"Freelance")'],
            ["CDI", '=COUNTIF(\'Job Offers Found\'!G:G,"CDI")'],
            ["CDD", '=COUNTIF(\'Job Offers Found\'!G:G,"CDD")'],
            [],
            ["REMOTE"],
            ["Mode", "Count"],
            ["Remote", '=COUNTIF(\'Job Offers Found\'!F:F,"Yes")'],
            ["On-site", '=COUNTIF(\'Job Offers Found\'!F:F,"No")'],
        ]
        ws.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")

        # Build batch requests: formatting + charts
        reqs = []

        # Title formatting
        reqs.append(_fmt_cells(sid, 0, 1, bold=True, size=16, bg=(0.2, 0.4, 0.7), fg=(1, 1, 1)))

        # Section headers
        for r in [2, 8, 15, 23, 29]:
            reqs.append(_fmt_cells(sid, r, r + 1, bold=True, size=11, bg=(0.85, 0.91, 0.98)))

        # Column widths
        reqs.append(_set_col_width(sid, 0, 1, 200))
        reqs.append(_set_col_width(sid, 1, 2, 100))

        # Move Dashboard to first tab
        reqs.append({
            "updateSheetProperties": {
                "properties": {"sheetId": sid, "index": 0},
                "fields": "index",
            }
        })

        # Charts
        reqs.append(_pie_chart_req(sid, "Jobs by Status", 4, 6, 2, 3))
        reqs.append(_pie_chart_req(sid, "Applications", 10, 13, 2, 8))
        reqs.append(_bar_chart_req(sid, "Score Distribution", 17, 22, 16, 3))
        reqs.append(_pie_chart_req(sid, "Contract Types", 25, 28, 16, 8))
        reqs.append(_pie_chart_req(sid, "Remote vs On-site", 31, 33, 30, 3))

        sh.batch_update({"requests": reqs})
        logger.info("Dashboard built successfully")

    except Exception as e:
        logger.error(f"Failed to build dashboard: {e}")
        raise


def _fmt_cells(sid, r1, r2, bold=False, size=10, bg=None, fg=None):
    """Build a repeatCell formatting request."""
    fmt = {"textFormat": {"bold": bold, "fontSize": size}}
    if fg:
        fmt["textFormat"]["foregroundColor"] = {"red": fg[0], "green": fg[1], "blue": fg[2]}
    if bg:
        fmt["backgroundColor"] = {"red": bg[0], "green": bg[1], "blue": bg[2]}
    return {
        "repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2, "startColumnIndex": 0, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": fmt},
            "fields": "userEnteredFormat(textFormat,backgroundColor)",
        }
    }


def _set_col_width(sid, c1, c2, px):
    """Build a column width request."""
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": c1, "endIndex": c2},
            "properties": {"pixelSize": px},
            "fields": "pixelSize",
        }
    }


def _pie_chart_req(sid, title, data_start, data_end, anchor_row, anchor_col):
    """Build an addChart request for a pie chart."""
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "pieChart": {
                        "legendPosition": "BOTTOM_LEGEND",
                        "domain": {"sourceRange": {"sources": [{"sheetId": sid, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": 0, "endColumnIndex": 1}]}},
                        "series": {"sourceRange": {"sources": [{"sheetId": sid, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": 1, "endColumnIndex": 2}]}},
                    },
                },
                "position": {"overlayPosition": {"anchorCell": {"sheetId": sid, "rowIndex": anchor_row, "columnIndex": anchor_col}, "widthPixels": 350, "heightPixels": 250}},
            }
        }
    }


def _bar_chart_req(sid, title, data_start, data_end, anchor_row, anchor_col):
    """Build an addChart request for a column/bar chart."""
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": "COLUMN",
                        "legendPosition": "NO_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "Score Range"},
                            {"position": "LEFT_AXIS", "title": "Count"},
                        ],
                        "domains": [{"domain": {"sourceRange": {"sources": [{"sheetId": sid, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": 0, "endColumnIndex": 1}]}}}],
                        "series": [{"series": {"sourceRange": {"sources": [{"sheetId": sid, "startRowIndex": data_start, "endRowIndex": data_end, "startColumnIndex": 1, "endColumnIndex": 2}]}}, "targetAxis": "LEFT_AXIS"}],
                        "headerCount": 0,
                    },
                },
                "position": {"overlayPosition": {"anchorCell": {"sheetId": sid, "rowIndex": anchor_row, "columnIndex": anchor_col}, "widthPixels": 350, "heightPixels": 250}},
            }
        }
    }


def track_application(
    date: str,
    platform: str,
    title: str,
    company: str,
    location: str,
    remote: bool,
    daily_rate_min: int = 0,
    daily_rate_max: int = 0,
    score: int = 0,
    status: str = "",
    application_result: str = "",
    external_url: str = "",
    url: str = "",
    proposal: str = "",
):
    """Append an application attempt to the 'Free-Work' worksheet."""
    try:
        ws = _get_or_create_worksheet("Free-Work", APPLICATION_HEADERS)
        row = [
            _format_date(date),
            platform,
            title,
            company,
            location,
            "Yes" if remote else "No",
            daily_rate_min,
            daily_rate_max,
            score,
            status,
            application_result,
            external_url,
            url,
            proposal,
        ]
        _append_row(ws, row)
        logger.info(f"Tracked application in 'Free-Work': {title[:50]}")
    except Exception as e:
        logger.error(f"Failed to track application in sheet: {e}")
