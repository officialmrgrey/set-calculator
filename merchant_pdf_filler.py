"""
merchant_pdf_filler.py  v2
Generates filled Canadian commercial production timesheets as a single PDF.
Supports both single-sheet and batch (department) JSON from the Set Calculator.

Usage:
    python merchant_pdf_filler.py input.json
    python merchant_pdf_filler.py input.json --out Grip_Day1.pdf

Output filename (if not specified):
  Single: {CrewName}_timesheet.pdf
  Batch:  {Department}_timesheets_{date}.pdf   (one PDF, all crew on separate pages)

Requirements:
    pip install reportlab
"""

import json
import sys
import argparse
from datetime import date
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors
from reportlab.lib.units import inch

PAGE_W, PAGE_H = letter
ML = 0.45 * inch
MR = PAGE_W - 0.45 * inch


def fc(val):
    try:
        f = float(val)
        return f"${f:.2f}" if f else ""
    except (TypeError, ValueError):
        return ""


def ff(val, decimals=1):
    try:
        f = float(val)
        return f"{f:.{decimals}f}" if f else ""
    except (TypeError, ValueError):
        return str(val) if val else ""


_CB_OFFSETS = {"Employee": 0, "Corporation": 115, "Daily (10h base)": 240}

def _cb_x(label):
    return _CB_OFFSETS.get(label, 0)


def _field_row(c, x0, x1, y, fields):
    total = x1 - x0
    x = x0
    c.setLineWidth(0.3)
    for label, value, frac in fields:
        w = total * frac
        c.setFont("Helvetica", 6.5)
        c.setFillColor(colors.HexColor("#8e8e93"))
        c.drawString(x + 2, y + 8, label)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9.5)
        c.drawString(x + 2, y - 3, str(value))
        c.line(x, y - 8, x + w - 4, y - 8)
        c.line(x + w - 4, y + 12, x + w - 4, y - 10)
        x += w


def _table_header(c, x0, y, col_w, headers, hdr_h):
    x = x0
    c.setLineWidth(0.3)
    for w, h in zip(col_w, headers):
        c.setFillColor(colors.HexColor("#f2f2f7"))
        c.rect(x, y - hdr_h, w, hdr_h, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 6.5)
        lines = h.split("\n")
        ty = y - 8 if len(lines) == 1 else y - 5
        for line in lines:
            c.drawCentredString(x + w / 2, ty, line)
            ty -= 8
        x += w


def _table_row(c, x0, y, col_w, vals, row_h, bold=False, label=None, label_col=None):
    x = x0
    c.setLineWidth(0.25)
    for i, (w, val) in enumerate(zip(col_w, vals)):
        c.rect(x, y - row_h, w, row_h)
        display = label if (label is not None and i == label_col) else str(val)
        if display:
            font = "Helvetica-Bold" if (bold or (label and i == label_col)) else "Helvetica"
            c.setFont(font, 7)
            c.drawCentredString(x + w / 2, y - row_h + 4, display)
        x += w


def draw_sheet(c: rl_canvas.Canvas, sheet: dict, page_num: int, total_pages: int):
    y = PAGE_H - 0.38 * inch

    # Header
    c.setFont("Helvetica-Bold", 15)
    c.drawString(ML, y, "PRODUCTION TIMESHEET")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#8e8e93"))
    c.drawRightString(MR, y, "Canadian commercial production · " + date.today().strftime("%Y-%m-%d"))
    if total_pages > 1:
        c.drawRightString(MR, y - 10, f"Sheet {page_num} of {total_pages}")
    c.setFillColor(colors.black)
    y -= 6
    c.setLineWidth(0.5)
    c.line(ML, y, MR, y)

    # Info rows
    y -= 20
    for row_fields in [
        [
            ("Job Name", sheet.get("jobName", ""), 0.38),
            ("Position", sheet.get("position", ""), 0.30),
            ("Job #", sheet.get("jobNum", ""), 0.16),
            ("Line #", sheet.get("lineNum", ""), 0.16),
        ],
        [
            ("Name", sheet.get("crewName", ""), 0.38),
            ("SIN # / Corp. Name", sheet.get("sinCorp", ""), 0.30),
            ("Daily Rate", fc(sheet.get("dailyRate")), 0.16),
            ("AHR", (fc(sheet.get("ahr")) + "/hr") if sheet.get("ahr") else "", 0.16),
        ],
    ]:
        _field_row(c, ML, MR, y, row_fields)
        y -= 28

    # Worker type badges
    worker_type = sheet.get("workerType", "employee")
    y -= 2
    c.setLineWidth(0.5)
    for label, checked in [
        ("Employee", worker_type == "employee"),
        ("Corporation", worker_type == "corporation"),
        ("Daily (10h base)", True),
    ]:
        ox = ML + _cb_x(label)
        c.rect(ox, y - 2, 8, 8)
        if checked:
            c.setFont("Helvetica-Bold", 8)
            c.drawString(ox + 1.5, y - 1, "X")
        c.setFont("Helvetica", 7.5)
        c.drawString(ox + 12, y + 4, label)

    y -= 14
    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(colors.HexColor("#8e8e93"))
    c.drawString(ML, y, "Note: Times as 24h decimal — e.g. 1:30pm = 13.5")
    c.setFillColor(colors.black)

    # Time table
    y -= 8
    total_w = MR - ML
    fracs = [0.09, 0.055, 0.055, 0.055, 0.055, 0.075, 0.075, 0.055, 0.055, 0.055, 0.065, 0.065, 0.08]
    col_w = [int(total_w * f) for f in fracs]
    col_w[-1] += int(total_w) - sum(col_w)

    headers = [
        "Date", "In", "Out", "Lunch", "Dinner",
        "Hrs\nWorked", "1x\n(flat=10)", "1.5x", "2x", "3x",
        "Meal\nPen.", "Total\nHrs", "Total\n$"
    ]
    HDR_H = 22
    _table_header(c, ML, y, col_w, headers, HDR_H)
    y -= HDR_H

    ahr = float(sheet.get("ahr") or 0)
    total_hrs = 0.0
    total_pay = 0.0
    ROW_H = 13

    for day in sheet.get("days", []):
        x1_h  = float(day.get("x1")  or 10)
        x15_h = float(day.get("x15") or 0)
        x2_h  = float(day.get("x2")  or 0)
        hrs   = float(day.get("hrs") or 0)
        pay   = ahr * (x1_h + x15_h * 1.5 + x2_h * 2)
        total_hrs += hrs
        total_pay += pay
        vals = [
            day.get("date", ""),
            ff(day.get("in")), ff(day.get("out")),
            ff(day.get("lunch")), "",
            ff(hrs), ff(x1_h), ff(x15_h) if x15_h else "", ff(x2_h) if x2_h else "", "",
            day.get("mealPen", ""),
            ff(hrs), fc(pay) if ahr else "",
        ]
        _table_row(c, ML, y, col_w, vals, ROW_H)
        y -= ROW_H

    # Blank filler rows
    for _ in range(max(0, 11 - len(sheet.get("days", [])))):
        _table_row(c, ML, y, col_w, [""] * 13, ROW_H)
        y -= ROW_H

    # Total row
    total_vals = [""] * 11 + [ff(total_hrs), fc(total_pay) if ahr else ""]
    _table_row(c, ML, y, col_w, total_vals, ROW_H, bold=True, label="TOTAL", label_col=10)
    y -= ROW_H + 8

    # Other earnings
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(ML, y, "OTHER EARNINGS")
    y -= 11
    oe_w = (MR - ML) / 3
    for i, (lbl, key) in enumerate([("Car", "carAmt"), ("Cell", "cellAmt"), ("Other", "otherAmt")]):
        ox = ML + i * oe_w
        c.setLineWidth(0.4)
        c.rect(ox, y - 14, oe_w - 4, 22)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#8e8e93"))
        c.drawString(ox + 4, y + 4, lbl)
        c.setFillColor(colors.black)
        val = fc(sheet.get(key))
        if val:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(ox + 4, y - 10, val)
    y -= 32

    # Signature line
    c.setLineWidth(0.5)
    sig_x = ML
    for lbl, sw in [("Crew Signature", 185), ("PM Approval", 145), ("Producer Approval", 120)]:
        c.line(sig_x, y, sig_x + sw, y)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(colors.HexColor("#8e8e93"))
        c.drawString(sig_x, y - 9, lbl)
        c.setFillColor(colors.black)
        sig_x += sw + 20

    # Footer
    y -= 26
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.HexColor("#8e8e93"))
    c.drawString(ML, y, "*Corporation: attach Incorporation Document + GST # on invoice.")
    c.setFillColor(colors.black)


def generate(json_path: str, out_path: str | None = None):
    with open(json_path) as f:
        data = json.load(f)

    sheets = data.get("sheets", [])
    if not sheets:
        sheets = [data]  # legacy single format

    if not out_path:
        if data.get("batch"):
            dept = data.get("dept", "Department")
            today = date.today().strftime("%Y-%m-%d")
            out_path = f"{dept}_timesheets_{today}.pdf"
        else:
            name = (sheets[0].get("crewName") or "timesheet").replace(" ", "_")
            out_path = f"{name}_timesheet.pdf"

    c = rl_canvas.Canvas(out_path, pagesize=letter)
    total = len(sheets)
    for i, sheet in enumerate(sheets, start=1):
        draw_sheet(c, sheet, i, total)
        if i < total:
            c.showPage()

    c.save()
    print(f"✓  Saved → {out_path}  ({total} page{'s' if total > 1 else ''})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Fill Canadian production timesheets from Set Calculator JSON."
    )
    ap.add_argument("json_file", help="JSON exported from timesheet.html")
    ap.add_argument("--out", default=None,
                    help="Output PDF filename (auto-named if omitted)")
    args = ap.parse_args()
    generate(args.json_file, args.out)
