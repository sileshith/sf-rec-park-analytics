"""Generate reproducible fictional permit transactions, without applicant data.

Run: python data_generator.py --rows 12000 --seed 1820
All distributions, fees, review durations, and service targets are modeling
assumptions, not SF Recreation and Park policy or observed performance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# Four analytical zones are invented groupings, not official department districts.
ZONES = ("North", "East", "South", "West")
CATEGORIES = ("Athletic Field", "Picnic Area", "Clubhouse", "Special Event")
# Category-specific assumed review days, service targets, and quoted fees in USD.
REVIEW_DAYS = np.array([9, 5, 12, 20])
TARGET_DAYS = np.array([14, 10, 21, 30])
BASE_FEES = np.array([150, 75, 300, 1200])


def generate_permits(
    rows: int = 12000,
    seed: int = 1820,
    start: str = "2025-01-01",
    as_of: str = "2026-09-30",
) -> pd.DataFrame:
    """Return a snapshot with decisions censored at the inclusive as-of date.

    Seasonal intake weights favor summer. Review durations are right-skewed,
    with deliberate category and zone effects so later analytics can detect
    modeled bottlenecks. Pending records have no future decision timestamps.
    Approval/rejection dates are mutually exclusive. Collected revenue is
    assumed paid in full on approval; pending/rejected records collect zero.
    """
    if rows < 1:
        raise ValueError("rows must be at least 1")
    first = pd.Timestamp(start).normalize()
    snapshot = pd.Timestamp(as_of).normalize()
    if first > snapshot:
        raise ValueError("start must be on or before as_of")
    rng = np.random.default_rng(seed)
    days = pd.date_range(first, snapshot, freq="D")
    weights = np.where(days.month.isin([5, 6, 7, 8]), 1.6, 1.0)
    submitted = pd.DatetimeIndex(rng.choice(days, rows, p=weights / weights.sum()))
    category = rng.choice(4, rows, p=[0.40, 0.32, 0.18, 0.10])
    zone = rng.choice(4, rows, p=[0.26, 0.30, 0.25, 0.19])
    lag = np.maximum(1, np.ceil(rng.gamma(2.5, 1 / 2.5, rows)
                              * REVIEW_DAYS[category]
                              * np.where(zone == 2, 1.25, 1.0))).astype(int)
    decision = submitted + pd.to_timedelta(lag, unit="D")
    resolved = decision <= snapshot
    approved = resolved & (rng.random(rows) < 0.88)
    rejected = resolved & ~approved
    quoted_cents = np.rint(BASE_FEES[category] * rng.uniform(0.75, 1.5, rows) * 100).astype(int)
    status = np.where(~resolved, "PENDING", np.where(approved, "APPROVED", "REJECTED"))
    frame = pd.DataFrame({
        "permit_id": [f"SYN-{i:07d}" for i in range(1, rows + 1)],
        "application_date": submitted,
        "approval_date": pd.Series(decision).where(approved),
        "rejection_date": pd.Series(decision).where(rejected),
        "permit_category": np.array(CATEGORIES)[category],
        "district_zone": np.array(ZONES)[zone],
        "status_code": status,
        "quoted_fee_cents": quoted_cents,
        "collected_fee_cents": np.where(approved, quoted_cents, 0),
        "service_target_days": TARGET_DAYS[category],
        "snapshot_date": snapshot,
        "is_synthetic": True,
    })
    validate_permits(frame)
    return frame


def validate_permits(frame: pd.DataFrame) -> None:
    """Reject broken snapshot, chronology, status, or revenue invariants."""
    if frame.empty or not frame.permit_id.is_unique:
        raise ValueError("Expected nonempty records with unique permit IDs")
    approved = frame.status_code.eq("APPROVED")
    rejected = frame.status_code.eq("REJECTED")
    if not frame.approval_date.notna().equals(approved):
        raise ValueError("Approval dates must agree with status")
    if not frame.rejection_date.notna().equals(rejected):
        raise ValueError("Rejection dates must agree with status")
    decision = frame.approval_date.fillna(frame.rejection_date)
    resolved = decision.notna()
    if ((decision[resolved] < frame.application_date[resolved]).any()
            or (decision[resolved] > frame.snapshot_date[resolved]).any()
            or (frame.application_date > frame.snapshot_date).any()):
        raise ValueError("Invalid timestamp ordering")
    if (frame.collected_fee_cents[~approved] != 0).any():
        raise ValueError("Only approvals may collect revenue")


def main() -> None:
    """Parse arguments, write CSV plus a reproducibility manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=1820)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--as-of", default="2026-09-30")
    parser.add_argument("--output", type=Path, default=Path("data/permits.csv"))
    args = parser.parse_args()
    try:
        frame = generate_permits(args.rows, args.seed, args.start, args.as_of)
    except (ValueError, OverflowError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False, date_format="%Y-%m-%d")
    manifest = {
        "synthetic": True, "schema_version": 1, "rows": len(frame),
        "seed": args.seed, "start": args.start, "as_of": args.as_of,
        "numpy_version": np.__version__, "pandas_version": pd.__version__,
        "status_counts": frame.status_code.value_counts().to_dict(),
        "assumptions": "Invented four-zone geography, fees, targets, seasonal intake, review lags, and approval rates. No official policy or operational observations.",
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(frame):,} synthetic permits to {args.output}")
    print(frame.status_code.value_counts().to_string())


if __name__ == "__main__":
    main()
