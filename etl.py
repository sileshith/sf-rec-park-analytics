"""Validate synthetic CSV, derive calendar-day KPIs, and publish SQLite atomically.

Run from the project directory: python etl.py
No official municipal SLA or fee policy is represented by this model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

import pandas as pd

from data_generator import CATEGORIES, ZONES, generate_permits, validate_permits

DATE_COLUMNS = ('application_date', 'approval_date', 'rejection_date', 'snapshot_date')
INTEGER_COLUMNS = ('quoted_fee_cents', 'collected_fee_cents', 'service_target_days')


def clean_permits(path: Path) -> pd.DataFrame:
    """Normalize text and reject invalid data instead of silently dropping rows."""
    required = list(generate_permits(1).columns)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}')
    df = df[required].apply(lambda column: column.str.strip())
    for name in DATE_COLUMNS:
        raw = df[name]
        parsed = pd.to_datetime(raw.replace('', None), format='%Y-%m-%d', errors='raise')
        if name in ('application_date', 'snapshot_date') and parsed.isna().any():
            raise ValueError(f'{name} cannot be blank')
        df[name] = parsed
    for name in INTEGER_COLUMNS:
        values = pd.to_numeric(df[name], errors='raise')
        if values.isna().any() or (values < 0).any() or (values % 1 != 0).any():
            raise ValueError(f'{name} must contain nonnegative integers')
        df[name] = values.astype('int64')
    if (df.service_target_days == 0).any():
        raise ValueError('Service targets must be positive')
    if not df.is_synthetic.str.lower().eq('true').all():
        raise ValueError('Only explicitly synthetic records are accepted')
    df['is_synthetic'] = True
    for name, allowed in [('permit_category', CATEGORIES), ('district_zone', ZONES),
                          ('status_code', ('APPROVED', 'REJECTED', 'PENDING'))]:
        if not df[name].isin(allowed).all():
            raise ValueError(f'Unknown or missing {name}')
    if not df.permit_id.str.fullmatch(r'SYN-\d+').all():
        raise ValueError('Expected synthetic permit IDs')
    if df.snapshot_date.nunique() != 1:
        raise ValueError('Input must represent exactly one snapshot date')
    validate_permits(df)
    approved = df.status_code.eq('APPROVED')
    if not df.loc[approved, 'collected_fee_cents'].equals(df.loc[approved, 'quoted_fee_cents']):
        raise ValueError('Approved revenue must match the modeled full-payment assumption')
    return df


def enrich_permits(df: pd.DataFrame) -> pd.DataFrame:
    """Add resolved turnaround, pending age, and strictly-over-target flags.

    A decision or pending age exactly on target is not overdue. A late resolved
    permit is a historical breach; an overdue pending permit is actionable backlog.
    """
    df = df.copy()
    df['decision_date'] = df.approval_date.fillna(df.rejection_date)
    pending = df.status_code.eq('PENDING')
    df['processing_days'] = (df.decision_date - df.application_date).dt.days.astype('Int64')
    df['pending_age_days'] = (df.snapshot_date - df.application_date).dt.days.where(pending).astype('Int64')
    df['resolved_late'] = (df.processing_days > df.service_target_days).fillna(False).astype(int)
    df['pending_overdue'] = (df.pending_age_days > df.service_target_days).fillna(False).astype(int)
    df['bottleneck_flag'] = df.pending_overdue
    df['days_over_target'] = (df.pending_age_days.fillna(df.processing_days) - df.service_target_days).clip(lower=0)
    return df


# Percentages use 0..100. Empty denominators yield NULL, never a misleading zero.
AGGREGATES = '''
 COUNT(*) AS total_permits,
 SUM(status_code = 'APPROVED') AS approved_permits,
 SUM(status_code = 'REJECTED') AS rejected_permits,
 SUM(status_code != 'PENDING') AS resolved_permits,
 SUM(status_code = 'PENDING') AS pending_permits,
 AVG(processing_days) AS avg_processing_days,
 AVG(CASE WHEN status_code = 'APPROVED' THEN processing_days END) AS avg_approval_days,
 AVG(CASE WHEN status_code = 'REJECTED' THEN processing_days END) AS avg_rejection_days,
 AVG(pending_age_days) AS avg_pending_age_days,
 SUM(collected_fee_cents) AS revenue_collected_cents,
 100.0 * SUM(status_code = 'PENDING') / COUNT(*) AS backlog_pct,
 SUM(resolved_late) AS resolved_late_count,
 SUM(pending_overdue) AS pending_overdue_count,
 100.0 * SUM(pending_overdue) / NULLIF(SUM(status_code = 'PENDING'), 0) AS pending_overdue_pct,
 100.0 * (SUM(status_code != 'PENDING') - SUM(resolved_late))
     / NULLIF(SUM(status_code != 'PENDING'), 0) AS resolved_within_target_pct
'''


def write_database(df: pd.DataFrame, output: Path, source_hash: str) -> dict:
    """Build a complete replacement in a temporary file, preserving old DB on failure."""
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix='.etl-', suffix='.sqlite', dir=output.parent)
    os.close(handle)
    try:
        with sqlite3.connect(temp_name) as conn:
            stored = df.copy()
            for name in (*DATE_COLUMNS, 'decision_date'):
                stored[name] = stored[name].dt.strftime('%Y-%m-%d').where(stored[name].notna(), None)
            stored.to_sql('permits', conn, index=False, if_exists='fail')
            conn.executescript('''
                CREATE UNIQUE INDEX permit_id_unique ON permits(permit_id);
                CREATE INDEX permits_filters ON permits(permit_category, district_zone, status_code);
                CREATE INDEX permits_application_date ON permits(application_date);
                CREATE VIEW bottleneck_applications AS
                  SELECT * FROM permits WHERE bottleneck_flag = 1;
                CREATE VIEW monthly_throughput AS
                  SELECT substr(decision_date, 1, 7) AS decision_month,
                    COUNT(*) AS decisions, SUM(status_code = 'APPROVED') AS approvals,
                    SUM(status_code = 'REJECTED') AS rejections,
                    AVG(processing_days) AS avg_processing_days,
                    SUM(collected_fee_cents) AS revenue_collected_cents
                  FROM permits WHERE decision_date IS NOT NULL GROUP BY decision_month;
            ''')
            conn.execute(f'CREATE VIEW executive_kpis AS SELECT {AGGREGATES} FROM permits')
            for name, group in [('category_kpis', 'permit_category'), ('zone_kpis', 'district_zone'),
                                ('category_zone_kpis', 'permit_category, district_zone')]:
                conn.execute(f'CREATE VIEW {name} AS SELECT {group}, {AGGREGATES}, '
                             '100.0 * SUM(collected_fee_cents) / '
                             'NULLIF((SELECT SUM(collected_fee_cents) FROM permits), 0) AS revenue_share_pct '
                             f'FROM permits GROUP BY {group}')
            metadata = {'schema_version': '1', 'source_sha256': source_hash,
                        'snapshot_date': df.snapshot_date.iloc[0].strftime('%Y-%m-%d'),
                        'synthetic': 'true', 'bottleneck_rule': 'PENDING and pending_age_days > service_target_days'}
            conn.execute('CREATE TABLE etl_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            conn.executemany('INSERT INTO etl_metadata VALUES (?, ?)', metadata.items())
            conn.row_factory = sqlite3.Row
            result = dict(conn.execute('SELECT * FROM executive_kpis').fetchone())
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite integrity check failed')
        os.replace(temp_name, output)
        return result
    finally:
        Path(temp_name).unlink(missing_ok=True)


def run_etl(source: Path, database: Path) -> dict:
    """Validate and load one snapshot; repeated runs replace it without duplicates."""
    if source.resolve() == database.resolve():
        raise ValueError('Input CSV and output database must differ')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return write_database(enrich_permits(clean_permits(source)), database, digest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('data/permits.csv'))
    parser.add_argument('--database', type=Path, default=Path('data/permits.sqlite'))
    args = parser.parse_args()
    try:
        result = run_etl(args.input, args.database)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.error(str(error))
    print(f'Synthetic snapshot loaded into {args.database}')
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
