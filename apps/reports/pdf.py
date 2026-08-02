"""Server-side branded PDF generation for report deliveries.

Replicates the design of the frontend jsPDF report (``src/lib/reportPdf.ts``):
light-yellow header band with the RPA logo, "PRINTED ON" date and downloader
name, report title, KPI stat tiles, labelled sections and data tables, and a
contact footer with page numbers on every page.

Uses ReportLab (pure Python, no system dependencies) so scheduled email
deliveries can attach a real branded PDF without a browser.
"""

from __future__ import annotations

import html
import io
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Brand palette (matches the platform UI and the frontend report — see the
# app screenshots: cream bg, slate-900 dark, amber/orange accents, teal
# amounts, green/red semantics)
# ---------------------------------------------------------------------------
DARK = colors.HexColor("#0d1424")  # active-nav navy from the app — titles, strong values
DARK_MID = colors.HexColor("#1e293b")  # slate-800 — table headers, section titles
HEADER_BG = colors.HexColor("#fff3bf")  # light yellow — header band (from the app hero gradient)
HEADER_SUB = colors.HexColor("#475569")  # slate-600 — secondary header text on the light band
GOLD = colors.HexColor("#f4b93f")  # accent strip, RPA kicker
TEAL = colors.HexColor("#1f6f78")  # brand teal — donor amounts
AMBER = colors.HexColor("#ea580c")  # orange-600 — Spent values
BODY = colors.HexColor("#334155")  # slate-700 — body/cell text on white
CARD_BG = colors.HexColor("#fcf9f2")  # app cream — KPI tiles + zebra rows
BORDER = colors.HexColor("#e4e8ee")
GRAY = colors.HexColor("#6b7280")
GRAY_LIGHT = colors.HexColor("#9ca3af")
GREEN = colors.HexColor("#15803d")  # green-700 — positive remaining / cleared status
RED = colors.HexColor("#dc2626")  # red-600 — over budget / deficits
WHITE = colors.HexColor("#ffffff")

ORG_NAME = "Rwanda Paediatric Association"
PLATFORM_NAME = "NGO Fund Platform"
LOGO_PATH = Path(__file__).resolve().parent / "static" / "reports" / "newlogo.png"

PAGE_W, PAGE_H = A4  # 595.28 x 841.89
MARGIN = 40
CONTENT_W = PAGE_W - MARGIN * 2  # 515.28
HEADER_BAND_H = 96
FOOTER_BOTTOM = 78  # distance from the page bottom to the footer zone top
TITLE_TOP = 142  # title baseline measured from the page top (matches jsPDF)
META_TOP = 162  # meta line baseline from the page top

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Exact snapshot keys that hold monetary amounts (formatted as currency).
AMOUNT_KEYS = {
    "total_grant_amount",
    "allocated_budget",
    "spent_amount",
    "remaining_balance",
    "budget_variance",
    "monthly_burn_rate",
    "contributions_received",
    "cleared_funds",
    "actual_spending",
    "remaining_funds",
    "amount_donated",
}

# Exact snapshot keys that hold percentages/rates (formatted as %).
PCT_KEYS = {"budget_utilization_percent", "reconciliation_rate"}

# Common currency symbols; letter codes render like Intl en-US ("RWF 500,000").
SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CHF": "CHF ",
    "CAD": "C$",
    "AUD": "A$",
    "NZD": "NZ$",
    "ZAR": "R ",
    "RWF": "RWF ",
    "KES": "KES ",
    "UGX": "UGX ",
    "TZS": "TZS ",
    "NGN": "₦",
    "GHS": "GH₵",
    "CDF": "FC ",
    "BIF": "FBu ",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _half_up(n: float) -> int:
    """Round half away from zero (matches Intl.NumberFormat's display rounding)."""
    if n >= 0:
        return int(math.floor(n + 0.5))
    return int(math.ceil(n - 0.5))


def format_currency(value: Any, code: str = "RWF") -> str:
    """Format an amount like the frontend (Intl en-US, no decimals).

    The sign goes before the symbol ("-RWF 470,000"), matching Intl output.
    """
    n = _num(value)
    symbol = SYMBOLS.get((code or "RWF").upper(), f"{code or 'RWF'} ")
    if n < 0:
        return f"-{symbol}{_half_up(abs(n)):,}"
    return f"{symbol}{_half_up(n):,}"


def _fmt_datetime(value: Any, with_time: bool = False) -> str:
    if value is None or value == "":
        return "—"
    dt = value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, datetime.min.time())
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        try:
            dt = timezone.localtime(dt)
        except (ValueError, OverflowError):
            pass
    s = f"{dt.day:02d} {MONTHS[dt.month - 1]} {dt.year}"
    if with_time:
        s += f", {dt.hour:02d}:{dt.minute:02d}"
    return s


def _titleize(key: str) -> str:
    s = re.sub(r"\b\w", lambda m: m.group(0).upper(), key.replace("_", " "))
    s = s.replace("Percent", "%").replace("Url", "URL").replace("Id", "ID")
    return s


def format_value(key: str, value: Any, currency: str) -> str:
    """Format a snapshot value: amounts as currency, rates as %, else plain."""
    if value is None or value == "":
        return "—"
    s = str(value)
    try:
        n = float(s)
    except ValueError:
        return s
    if key in PCT_KEYS:
        return f"{n}%"
    if key in AMOUNT_KEYS:
        return format_currency(n, currency)
    return s


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None and value != "" else "—"))


def _hex(color) -> str:
    """Palette color → '#rrggbb' for use inside Paragraph font tags."""
    return "#%02x%02x%02x" % (
        int(round(color.red * 255)),
        int(round(color.green * 255)),
        int(round(color.blue * 255)),
    )


# ---------------------------------------------------------------------------
# Paragraph styles
# ---------------------------------------------------------------------------

def _style(**kwargs) -> ParagraphStyle:
    defaults = dict(fontName="Helvetica", fontSize=9, leading=12, textColor=BODY)
    defaults.update(kwargs)
    return ParagraphStyle("cell", **defaults)


_SECTION = ParagraphStyle(
    "section",
    fontName="Helvetica-Bold",
    fontSize=9,
    leading=12,
    textColor=DARK_MID,
    spaceBefore=16,
    spaceAfter=6,
)
_LABEL = _style(fontName="Helvetica", fontSize=9, textColor=GRAY)
_VALUE = _style(fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT)
_HEADER = _style(fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=WHITE)
_CELL = _style(fontName="Helvetica", fontSize=9)
_CELL_RIGHT = _style(fontName="Helvetica", fontSize=9, alignment=TA_RIGHT)
_CELL_BOLD_RIGHT = _style(fontName="Helvetica-Bold", fontSize=9, alignment=TA_RIGHT)
_CELL_GRAY = _style(fontName="Helvetica", fontSize=9, textColor=GRAY)
_CELL_GRAY_RIGHT = _style(fontName="Helvetica", fontSize=9, textColor=GRAY, alignment=TA_RIGHT)
_NOTE = _style(fontName="Helvetica", fontSize=10, leading=14, textColor=GRAY, alignment=TA_CENTER)


# ---------------------------------------------------------------------------
# Flowables / drawing
# ---------------------------------------------------------------------------

class KpiTiles(Flowable):
    """Four stat tiles in the system palette (mirrors the frontend drawKpiTiles)."""

    def __init__(self, tiles, width: float = CONTENT_W):
        super().__init__()
        self.tiles = tiles  # list of (label, value, color)
        self.width = width
        self.height = 64

    def _fit(self, text: str, font: str, size: float, max_width: float) -> str:
        c = self.canv
        if c.stringWidth(text, font, size) <= max_width:
            return text
        while text and c.stringWidth(text + "…", font, size) > max_width:
            text = text[:-1]
        return text + "…"

    def draw(self):
        # The canvas is translated to this flowable's origin, so draw locally.
        c = self.canv
        gap = 10
        n = len(self.tiles)
        w = (self.width - gap * (n - 1)) / n
        for i, (label, value, color) in enumerate(self.tiles):
            x = i * (w + gap)
            c.setFillColor(CARD_BG)
            c.setStrokeColor(BORDER)
            c.setLineWidth(0.7)
            c.roundRect(x, 0, w, self.height, 6, fill=1, stroke=1)

            c.setFont("Helvetica-Bold", 7)
            c.setFillColor(GRAY_LIGHT)
            c.drawCentredString(x + w / 2, self.height - 20, label.upper())

            long = len(value) > 15
            size = 11 if long else 15
            c.setFont("Helvetica-Bold", size)
            c.setFillColor(color)
            fitted = self._fit(value, "Helvetica-Bold", size, w - 8)
            c.drawCentredString(x + w / 2, 21, fitted)


def _draw_header_band(
    c: canvas.Canvas,
    logo: Optional[ImageReader],
    recipient_name: str,
    recipient_email: Optional[str],
    now_iso: str,
):
    """Light-yellow band with logo/branding on the left and print meta on the right."""
    # Light-yellow full-bleed band
    c.setFillColor(HEADER_BG)
    c.rect(0, PAGE_H - HEADER_BAND_H, PAGE_W, HEADER_BAND_H, stroke=0, fill=1)

    text_x = MARGIN
    if logo is not None:
        try:
            c.drawImage(logo, MARGIN, PAGE_H - 20 - 52, width=66, height=52, preserveAspectRatio=True, mask="auto")
            text_x = MARGIN + 78
        except Exception:  # pragma: no cover - logo is decorative
            text_x = MARGIN

    # Left: RPA / platform / org
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(DARK)
    c.drawString(text_x, PAGE_H - 34, "RPA")

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(DARK)
    c.drawString(text_x, PAGE_H - 52, PLATFORM_NAME)

    c.setFont("Helvetica", 8.5)
    c.setFillColor(HEADER_SUB)
    c.drawString(text_x, PAGE_H - 66, ORG_NAME)

    # Right: print date + downloader
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(DARK)
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 34, f"PRINTED ON {_fmt_datetime(now_iso, True)}".upper())

    c.setFont("Helvetica", 9.5)
    c.setFillColor(HEADER_SUB)
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 52, f"Downloaded by: {recipient_name or 'Unknown user'}")

    if recipient_email:
        c.setFont("Helvetica", 8)
        c.setFillColor(HEADER_SUB)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - 66, recipient_email)

    # Gold accent strip
    c.setFillColor(GOLD)
    c.rect(0, PAGE_H - HEADER_BAND_H - 4, PAGE_W, 4, stroke=0, fill=1)


def _draw_title_block(
    c: canvas.Canvas,
    report_type: str,
    grant_title: str,
    fmt_label: str,
    created_at: Any,
):
    base = (report_type or "Report").strip().upper()
    title = base if base.endswith("REPORT") else f"{base} REPORT"

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(DARK)
    words = title.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if not current or c.stringWidth(test, "Helvetica-Bold", 20) <= CONTENT_W:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    lines = lines[:2]
    for i, line in enumerate(lines):
        c.drawCentredString(PAGE_W / 2, PAGE_H - TITLE_TOP - i * 24, line)

    # When the title wraps to two lines, shift the meta line down so the
    # second title line (at PAGE_H - 166) never collides with it.
    meta_top = META_TOP + (16 if len(lines) > 1 else 0)
    c.setFont("Helvetica", 9.5)
    c.setFillColor(GRAY)
    c.drawCentredString(
        PAGE_W / 2,
        PAGE_H - meta_top,
        f"{grant_title}   ·   {fmt_label}   ·   Generated {_fmt_datetime(created_at)}",
    )


def _draw_footer(c: canvas.Canvas, page_num: int, total_pages: int, recipient_name: str, destination: str):
    y = FOOTER_BOTTOM
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.7)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)

    c.setFont("Helvetica", 8.5)
    c.setFillColor(GRAY)
    c.drawCentredString(
        PAGE_W / 2,
        y + 18,
        f"This is a report downloaded by {recipient_name or 'Unknown user'}. No signature required.",
    )

    c.setFont("Helvetica", 8)
    c.setFillColor(GRAY_LIGHT)
    c.drawCentredString(PAGE_W / 2, y + 32, f"{PLATFORM_NAME} · {ORG_NAME} — Kigali, Rwanda")

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(GRAY)
    c.drawRightString(PAGE_W - MARGIN, y + 32, f"Page {page_num} of {total_pages}")


def _section_title(text: str) -> Paragraph:
    return Paragraph(_esc(text).upper(), _SECTION)


def _label_value_table(data: dict, currency: str) -> Table:
    rows = [
        [
            Paragraph(_esc(_titleize(k)), _LABEL),
            Paragraph(_esc(format_value(k, v, currency)), _VALUE),
        ]
        for k, v in data.items()
    ]
    table = Table(rows, colWidths=[205, CONTENT_W - 205], hAlign="LEFT", repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    return table


def _data_table(header: list[str], rows: list[list[Paragraph]], col_widths: list[float]) -> Table:
    header_cells = [Paragraph(_esc(h).upper(), _HEADER) for h in header]
    body = [header_cells] + rows
    table = Table(body, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK_MID),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    for row_idx in range(2, len(body), 2):  # zebra on odd data rows (matches jsPDF)
        style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), CARD_BG))
    table.setStyle(TableStyle(style))
    return table


def _budget_lines_table(lines: list[dict], currency: str) -> Table:
    rows: list[list[Paragraph]] = []
    for bl in lines:
        remaining = _num(bl.get("remaining_amount"))
        remaining_color = _hex(RED) if remaining < 0 else _hex(GREEN)
        rows.append(
            [
                Paragraph(_esc(bl.get("line_name")), _CELL),
                Paragraph(_esc(format_currency(bl.get("allocated_amount"), currency)), _CELL_RIGHT),
                Paragraph(_esc(format_currency(bl.get("spent_amount"), currency)), _CELL_RIGHT),
                Paragraph(
                    f'<font color="{remaining_color}"><b>{_esc(format_currency(bl.get("remaining_amount"), currency))}</b></font>',
                    _CELL_RIGHT,
                ),
            ]
        )
    return _data_table(["Line", "Allocated", "Spent", "Remaining"], rows, [200, 105, 105, 105])


def _transactions_table(transactions: list[dict], budget_lines: list[dict], currency: str) -> Table:
    line_names = {str(bl.get("id")): bl.get("line_name") or "" for bl in budget_lines}
    rows: list[list[Paragraph]] = []
    for txn in transactions[:40]:
        status = str(txn.get("status") or "—").upper()
        status_color = _hex(GREEN) if status.lower() in ("cleared", "reconciled") else _hex(GRAY)
        line_name = line_names.get(str(txn.get("budget_line"))) or f"Line #{txn.get('budget_line') or '—'}"
        txn_currency = (txn.get("currency") or currency or "RWF")
        rows.append(
            [
                Paragraph(_esc(_fmt_datetime(txn.get("transaction_date"))), _CELL_GRAY),
                Paragraph(_esc(txn.get("bank_reference_number") or "—"), _CELL),
                Paragraph(_esc(line_name), _CELL),
                Paragraph(f"<b>{_esc(format_currency(txn.get('amount'), txn_currency))}</b>", _CELL_BOLD_RIGHT),
                Paragraph(f'<font color="{status_color}">{_esc(status)}</font>', _CELL),
            ]
        )
    return _data_table(["Date", "Reference", "Budget Line", "Amount", "Status"], rows, [85, 105, 120, 95, 110])


def _projects_table(projects: list[dict]) -> Table:
    rows: list[list[Paragraph]] = []
    for project in projects:
        rows.append(
            [
                Paragraph(f"<b>{_esc(project.get('name'))}</b>", _CELL),
                Paragraph(_esc(str(project.get("status") or "—").upper()), _CELL_GRAY),
                Paragraph(_esc(_fmt_datetime(project.get("start_date"))), _CELL_GRAY),
                Paragraph(_esc(_fmt_datetime(project.get("end_date"))), _CELL_GRAY),
            ]
        )
    return _data_table(["Project", "Status", "Start", "End"], rows, [215, 90, 105, 105])


def _audit_references_table(references: list[dict]) -> Table:
    rows: list[list[Paragraph]] = []
    for log in references[:10]:
        rows.append(
            [
                Paragraph(_esc(_fmt_datetime(log.get("timestamp"), True)), _CELL_GRAY),
                Paragraph(_esc(_titleize(str(log.get("action_type") or "—"))), _CELL),
                Paragraph(_esc(_titleize(str(log.get("target_entity_type") or "—"))), _CELL),
                Paragraph(_esc(str(log.get("target_entity_id") or "—")), _CELL_GRAY_RIGHT),
            ]
        )
    return _data_table(["Timestamp", "Action", "Entity", "ID"], rows, [120, 160, 115, 120])


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------

def _canvas_factory(recipient_name: str, destination: str) -> Callable:
    """Return a canvas class that stamps the footer with 'Page X of Y' on save."""

    class _NumberedCanvas(canvas.Canvas):  # type: ignore[misc]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states: list[dict] = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total_pages = len(self._saved_page_states)
            for page_num, state in enumerate(self._saved_page_states, start=1):
                self.__dict__.update(state)
                _draw_footer(self, page_num, total_pages, recipient_name, destination)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

    return _NumberedCanvas


def build_report_pdf(
    report,
    *,
    recipient_name: str = "Unknown user",
    recipient_email: Optional[str] = None,
    now=None,
) -> bytes:
    """Build the branded report PDF as bytes from a Report and its snapshot."""
    now_dt = now or timezone.now()
    custom_fields = report.custom_fields or {}
    snap = custom_fields.get("snapshot") or {}
    grant = snap.get("grant") or {}
    currency = grant.get("currency") or "RWF"
    grant_title = grant.get("grant_title") or (f"Grant #{report.grant_id}" if report.grant_id else "All Grants")

    logo: Optional[ImageReader] = None
    if LOGO_PATH.exists():
        try:
            logo = ImageReader(str(LOGO_PATH))
        except Exception:  # pragma: no cover - decorative
            logo = None

    destination = recipient_email or recipient_name

    # --- story -----------------------------------------------------------------
    story: list[Any] = []
    # Reserve space for the header band (100pt) + title block (content starts at y=182).
    story.append(Spacer(1, 182 - 40))  # topMargin is 40

    fs = snap.get("financial_summary") or {}
    if snap and len(snap) > 0:
        spent = _num(fs.get("spent_amount"))
        allocated = _num(fs.get("allocated_budget"))
        remaining = _num(fs.get("remaining_balance"))
        grant_total = grant.get("total_amount") or fs.get("total_grant_amount")
        story.append(
            KpiTiles(
                [
                    ("Total Grant", format_currency(grant_total, currency), DARK),
                    ("Allocated Budget", format_currency(fs.get("allocated_budget"), currency), DARK),
                    ("Spent", format_currency(fs.get("spent_amount"), currency), AMBER),
                    ("Remaining", format_currency(fs.get("remaining_balance"), currency), RED if remaining < 0 else GREEN),
                ]
            )
        )
        story.append(Spacer(1, 18))

    for title, data in [
        ("Financial Summary", fs),
        ("Donor Funding", snap.get("donor_funding")),
        ("Project Utilization", snap.get("project_utilization")),
        ("Reconciliation", snap.get("reconciliation_report")),
        ("Audit & Compliance", snap.get("audit_compliance_report")),
    ]:
        if data and isinstance(data, dict) and data:
            story.append(_section_title(title))
            story.append(_label_value_table(data, currency))

    budget_lines = snap.get("budget_lines") or []
    if budget_lines:
        story.append(_section_title("Budget Lines"))
        story.append(_budget_lines_table(budget_lines, currency))

    transactions = snap.get("transactions") or []
    if transactions:
        story.append(_section_title("Transactions"))
        story.append(_transactions_table(transactions, budget_lines, currency))

    projects = snap.get("projects") or []
    if projects:
        story.append(_section_title("Projects"))
        story.append(_projects_table(projects))

    audit_references = snap.get("audit_references") or []
    if audit_references:
        story.append(_section_title("Audit Trail References"))
        story.append(_audit_references_table(audit_references))

    if not snap or len(snap) == 0:
        story.append(Paragraph("No report data is available for this report.", _NOTE))

    # --- assemble --------------------------------------------------------------
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=40,
        bottomMargin=FOOTER_BOTTOM,
        title=f"{report.report_type} - {PLATFORM_NAME}",
        author=recipient_name,
    )

    def on_first_page(c, _d):
        _draw_header_band(c, logo, recipient_name, recipient_email, now_dt.isoformat())
        _draw_title_block(c, report.report_type, grant_title, report.format, report.created_at)

    # NB: canvasmaker must be passed to build() — the constructor value is
    # ignored because BaseDocTemplate.build() defaults it to canvas.Canvas.
    doc.build(story, onFirstPage=on_first_page, canvasmaker=_canvas_factory(recipient_name, destination))
    return buf.getvalue()


def report_pdf_filename(report_type: str, now=None) -> str:
    """NGO_Fund_Platform_<type>_<date>.pdf — same naming as the frontend."""
    now_dt = now or timezone.now()
    slug = re.sub(r"[^a-z0-9]+", "-", (report_type or "report").lower()).strip("-")
    return f"NGO_Fund_Platform_{slug}_{now_dt.strftime('%Y-%m-%d')}.pdf"
