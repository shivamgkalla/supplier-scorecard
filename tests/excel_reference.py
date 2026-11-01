"""A stand-in for the legacy spreadsheet model.

Builds a workbook whose scoring is done entirely by Excel formulas (approximate-match
VLOOKUPs into band tables, a weighted sum, a tier lookup), the way such models are
usually built by hand. LibreOffice then calculates it, and the tests check that the
Python pipeline gives the same answers.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook

from scorecard.features import FEATURE_COLUMNS
from scorecard.scoring import Config


def soffice_path():
    return shutil.which("soffice") or shutil.which("libreoffice")


def build_reference_workbook(features: pd.DataFrame, cfg: Config, path: Path) -> None:
    wb = Workbook()

    inputs = wb.active
    inputs.title = "Inputs"
    inputs.append(["supplier_id"] + FEATURE_COLUMNS)
    for row in features[["supplier_id"] + FEATURE_COLUMNS].itertuples(index=False):
        inputs.append(list(row))

    bands = wb.create_sheet("Bands")
    ranges = {}
    for i, f in enumerate(cfg.features):
        col_t, col_p = 1 + 2 * i, 2 + 2 * i
        bands.cell(row=1, column=col_t, value=f"{f.name} threshold")
        bands.cell(row=1, column=col_p, value=f"{f.name} points")
        for r, (t, p) in enumerate(zip(f.thresholds, f.points), start=2):
            bands.cell(row=r, column=col_t, value=t)
            bands.cell(row=r, column=col_p, value=p)
        a, b = bands.cell(row=2, column=col_t).coordinate, bands.cell(row=1 + len(f.points), column=col_p).coordinate
        ranges[f.name] = f"Bands!${a[0]}${a[1:]}:${b[0]}${b[1:]}"

    weights = wb.create_sheet("Weights")
    for r, f in enumerate(cfg.features, start=1):
        weights.cell(row=r, column=1, value=f.name)
        weights.cell(row=r, column=2, value=f.weight)

    tiers = wb.create_sheet("Tiers")
    tiers.append(["min score", "tier"])
    for t, n in zip(cfg.tier_thresholds, cfg.tier_names):
        tiers.append([t, n])
    tier_range = f"Tiers!$A$2:$B${1 + len(cfg.tier_names)}"

    model = wb.create_sheet("Model")
    model.append(["supplier_id"] + [f"{f.name}_points" for f in cfg.features] + ["score", "risk_tier"])
    for r in range(2, len(features) + 2):
        row = [f"=Inputs!A{r}"]
        for i, f in enumerate(cfg.features):
            input_cell = f"Inputs!{chr(ord('B') + i)}{r}"
            row.append(f"=VLOOKUP({input_cell},{ranges[f.name]},2,TRUE)")
        weighted = "+".join(f"Weights!$B${k}*{chr(ord('B') + k - 1)}{r}" for k in range(1, len(cfg.features) + 1))
        row.append(f"=({weighted})/100")
        row.append(f"=VLOOKUP(G{r},{tier_range},2,TRUE)")
        model.append(row)
    wb.save(path)


def recalculate(path: Path, workdir: Path) -> Path:
    """Open the workbook in LibreOffice (which calculates every formula) and save a copy."""
    out = workdir / "calculated"
    out.mkdir(exist_ok=True)
    profile = workdir / "lo_profile"
    subprocess.run(
        [
            soffice_path(),
            f"-env:UserInstallation=file://{profile}",
            "--headless",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(out),
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    return out / path.name


def read_model(path: Path) -> pd.DataFrame:
    ws = load_workbook(path, data_only=True)["Model"]
    rows = list(ws.iter_rows(values_only=True))
    return pd.DataFrame(rows[1:], columns=rows[0])
