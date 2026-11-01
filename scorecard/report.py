"""Write the Excel report: summary, full scores with every step, and an exceptions list."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .scoring import INSUFFICIENT, Config, tier_counts

TIER_FILL = {
    "Critical": "F4B6B6",
    "High": "F8D7A8",
    "Medium": "FBEFA6",
    "Low": "CFE8CF",
    INSUFFICIENT: "DDDDDD",
}
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")


def _write_frame(ws, df: pd.DataFrame, number_formats: dict) -> None:
    ws.append(list(df.columns))
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in df.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and pd.isna(v)) else v for v in row])
    for idx, col in enumerate(df.columns, start=1):
        letter = get_column_letter(idx)
        ws.column_dimensions[letter].width = max(12, min(28, len(str(col)) + 4))
        fmt = number_formats.get(col)
        if fmt:
            for cell in ws[letter][1:]:
                cell.number_format = fmt
    ws.freeze_panes = "B2"
    if tier_col := (list(df.columns).index("risk_tier") + 1 if "risk_tier" in df.columns else None):
        for r in range(2, ws.max_row + 1):
            cell = ws.cell(row=r, column=tier_col)
            if cell.value in TIER_FILL:
                cell.fill = PatternFill("solid", fgColor=TIER_FILL[cell.value])


def build_report(scored: pd.DataFrame, cfg: Config) -> bytes:
    wb = Workbook()

    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "Supplier risk scorecard"
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    ws.append(["Risk tier", "Suppliers"])
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
    for tier, n in tier_counts(scored, cfg).items():
        ws.append([tier, n])
        ws.cell(row=ws.max_row, column=1).fill = PatternFill("solid", fgColor=TIER_FILL[tier])
    ws.append([])
    ws.append(["Total suppliers", int(len(scored))])
    ws.append(["Minimum delivered orders to be scored", cfg.min_orders])
    ws.append([])
    ws.append(["Weights (score = sum of weight x points / 100)"])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    for f in cfg.features:
        ws.append([f.name, f.weight])
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 14

    detail = scored.copy()
    fmt = {c: "0.0%" for c in ["on_time_rate", "fill_rate", "reject_rate", "price_variance"]}
    fmt.update({"avg_delay_days": "0.0", "score": "0.0", "points_lost": "0.0"})
    _write_frame(wb.create_sheet("Scores"), detail, fmt)

    exceptions = scored[scored["risk_tier"].isin(["Critical", "High"])][
        ["supplier_id", "score", "risk_tier", "main_driver", "points_lost", "n_orders"]
    ]
    _write_frame(wb.create_sheet("Exceptions"), exceptions, fmt)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
