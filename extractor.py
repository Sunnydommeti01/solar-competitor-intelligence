"""District-wise PM Surya Ghar vendor extraction and Excel export.

Requires api_client.VendorAPIClient configured with a verified encrypted
request builder. Does not use CSV or pretend live API access is configured.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo
from typing import Any, Iterable

import pandas as pd
from api_client import VendorAPIClient, VendorAPIError

COLUMNS = ["State", "District", "Vendor ID", "Vendor Name", "Installations"]


def _vendor_list(payload: Any) -> list[dict]:
    """Accept a plain vendor list or common JSON response wrappers.

    Unknown response structures raise rather than silently report zero vendors.
    """
    if isinstance(payload, list):
        if not all(isinstance(item, dict) for item in payload):
            raise ValueError("Vendor response list contains non-object entries")
        return payload
    if isinstance(payload, dict):
        for key in ("data", "result", "response", "vendors", "vendorList"):
            if key in payload:
                return _vendor_list(payload[key])
    raise ValueError("Unrecognized API response structure; inspect actual response JSON")


def normalize_vendors(payload: Any, state: str, district: str) -> pd.DataFrame:
    rows = []
    for vendor in _vendor_list(payload):
        details = vendor.get("districtwiseInstallationAndCapacity")
        count = details.get("installationCount") if isinstance(details, dict) else None
        rows.append({
            "State": state,
            "District": district,
            "Vendor ID": vendor.get("vendorId"),
            "Vendor Name": vendor.get("vendorName"),
            "Installations": count,
        })
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["Installations"] = pd.to_numeric(df["Installations"], errors="coerce").astype("Int64")
    # Keep vendor rows without IDs; do not accidentally collapse all missing IDs.
    with_id = df[df["Vendor ID"].notna()].drop_duplicates(
        subset=["State", "District", "Vendor ID"], keep="first"
    )
    without_id = df[df["Vendor ID"].isna()]
    return pd.concat([with_id, without_id], ignore_index=True)


def extract_district(state: str, district: str, client: VendorAPIClient) -> pd.DataFrame:
    """Fetch one district; raises when encrypted API integration is unavailable."""
    payload = client.fetch_vendors(state, district)
    return normalize_vendors(payload, state, district)


def extract_all(districts_by_state: dict[str, Iterable[str]], client: VendorAPIClient) -> pd.DataFrame:
    """Fetch each district independently; fail rather than silently omit districts."""
    frames = []
    for state, districts in districts_by_state.items():
        for district in districts:
            try:
                frames.append(extract_district(state, district, client))
            except (VendorAPIError, ValueError) as exc:
                raise RuntimeError(f"Extraction failed for {state} / {district}: {exc}") from exc
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Build an in-memory Excel download, without writing a CSV to GitHub."""
    output = BytesIO()
    date_label = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%m-%Y")
    export = df.rename(columns={"Installations": f"Installations ({date_label})"})
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export.to_excel(writer, index=False, sheet_name="Vendor Comparison")
        sheet = writer.sheets["Vendor Comparison"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for col in sheet.columns:
            letter = col[0].column_letter
            sheet.column_dimensions[letter].width = min(
                max(14, max(len(str(cell.value or "")) for cell in col) + 2), 45
            )
    return output.getvalue()


if __name__ == "__main__":
    # This is a real API smoke test; it will clearly fail until the
    # encrypted request builder and credentials are configured.
    try:
        result = extract_district("Andhra Pradesh", "Eluru", VendorAPIClient())
        print(result.head().to_string(index=False))
    except VendorAPIError as exc:
        print(f"Live extraction not configured: {exc}")
