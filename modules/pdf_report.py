"""
PDF report generator — turns the filtered CSV log data (from modules/reports.py)
into a clean, government-portal-style PDF: letterhead (with real institutional
logos), section title, period, generated timestamp, and a data table.
"""
import io
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors as rl_colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

import config
from modules import reports as reports_mod

SECTION_TITLES = {
    "gate": "Gate 1 — Vehicle IN/OUT Log",
    "vehicle": "Vehicle Entry/Exit Counter Log",
    "plate": "Gate 1 — ANPR / Number Plate Log",
    "waste_primary": "Conveyor 1 — Primary Segregation (Metal vs Other)",
    "waste_secondary": "Conveyor 2 — Secondary Plastic Classification",
    "thief": "PWMU Shed — Security & Anomaly Alerts",
}

NAVY = rl_colors.HexColor("#1E3A8A")
LIGHT_ROW = rl_colors.HexColor("#F8FAFC")
BORDER = rl_colors.HexColor("#CBD5E1")

_LOGO_DIR = os.path.join(config.BASE_DIR, "static", "images")
_LOGO_FILES = ["logo_nit_raipur.png", "logo_cg_govt.png", "logo_unicef.png"]


def _doc(buf):
    return SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                              leftMargin=1.5 * cm, rightMargin=1.5 * cm)


def _logo_row():
    """Three institutional logos side-by-side, if the image files exist."""
    cells = []
    for fname in _LOGO_FILES:
        path = os.path.join(_LOGO_DIR, fname)
        if os.path.exists(path):
            cells.append(Image(path, width=3.2 * cm, height=1.4 * cm, kind="proportional"))
        else:
            cells.append("")
    if not any(cells):
        return []
    t = Table([cells], colWidths=[5.5 * cm] * 3)
    t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return [t, Spacer(1, 8)]


def _letterhead(period):
    styles = getSampleStyleSheet()
    centered = ParagraphStyle("centered_small", parent=styles["Normal"], alignment=1,
                               fontSize=9, textColor=rl_colors.HexColor("#475569"))
    centered_normal = ParagraphStyle("centered_normal", parent=styles["Normal"], alignment=1)
    flow = _logo_row() + [
        Paragraph("NIT RAIPUR | GOVERNMENT OF CHHATTISGARH | UNICEF", centered),
        Spacer(1, 10),
        Paragraph("<b>Ecobyte — Smart PWMU / MRF Intelligence System</b>", styles["Title"]),
        Paragraph("Digital India Initiative &nbsp;·&nbsp; Swachh Bharat Mission &nbsp;·&nbsp; Team Ecobyte × Robosapiens, NIT Raipur", centered_normal),
        Spacer(1, 4),
        Paragraph(f"Report Period: <b>{period.title()}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}", centered_normal),
        Spacer(1, 14),
    ]
    return flow


def _section_heading(title):
    styles = getSampleStyleSheet()
    return [Paragraph(f"<b>{title}</b>", styles["Heading2"]), Spacer(1, 6)]


def _table(rows, max_cols=8):
    styles = getSampleStyleSheet()
    if not rows:
        return [Paragraph("No records found for this period.", styles["Normal"]), Spacer(1, 12)]

    headers = list(rows[0].keys())[:max_cols]
    data = [headers] + [[str(r.get(h, ""))[:40] for h in headers] for r in rows]
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, LIGHT_ROW]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [t, Spacer(1, 16)]


def build_module_pdf(module: str, period: str = "all"):
    rows = reports_mod.read_filtered(module, period)
    title = SECTION_TITLES.get(module, module.replace("_", " ").title())

    buf = io.BytesIO()
    flow = _letterhead(period) + _section_heading(title) + _table(rows)
    _doc(buf).build(flow)
    buf.seek(0)
    filename = f"{module}_report_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return filename, buf.read()


def build_gate_pdf(period: str = "all"):
    """Gate section covers BOTH vehicle counting and ANPR — one combined PDF."""
    vehicle_rows = reports_mod.read_filtered("gate", period)
    plate_rows = reports_mod.read_filtered("plate", period)

    buf = io.BytesIO()
    flow = _letterhead(period)
    flow += _section_heading("Vehicle IN/OUT Log")
    flow += _table(vehicle_rows)
    flow += _section_heading("ANPR / Number Plate Log")
    flow += _table(plate_rows)
    _doc(buf).build(flow)
    buf.seek(0)
    filename = f"gate_report_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return filename, buf.read()


def build_full_pdf(period: str = "all"):
    """Section 5 — Overall Operations & Audit Summary: one PDF, one section per module."""
    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    flow = _letterhead(period)
    flow.append(Paragraph("<b>Consolidated Operations &amp; Digital Audit Trail</b>", styles["Heading1"]))
    flow.append(Spacer(1, 10))

    for module in ["gate", "plate", "waste_primary", "waste_secondary", "thief"]:
        rows = reports_mod.read_filtered(module, period)
        flow += _section_heading(SECTION_TITLES.get(module, module.title()))
        flow += _table(rows)

    _doc(buf).build(flow)
    buf.seek(0)
    filename = f"pwmu_full_report_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return filename, buf.read()
