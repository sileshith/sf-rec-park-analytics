"""Focused ETL checks: python -m unittest -v test_etl.py."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data_generator import generate_permits
from etl import run_etl


class ETLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'permits.csv'
        self.db = Path(self.temp.name) / 'permits.sqlite'
        self.frame = generate_permits(4)
        self.frame['application_date'] = pd.Timestamp('2026-09-20')
        self.frame['snapshot_date'] = pd.Timestamp('2026-09-30')
        self.frame['status_code'] = ['APPROVED', 'REJECTED', 'PENDING', 'PENDING']
        self.frame['approval_date'] = pd.to_datetime(['2026-09-25', None, None, None])
        self.frame['rejection_date'] = pd.to_datetime([None, '2026-09-26', None, None])
        self.frame['service_target_days'] = [5, 5, 10, 9]
        self.frame['quoted_fee_cents'] = [10000] * 4
        self.frame['collected_fee_cents'] = [10000, 0, 0, 0]

    def load(self):
        self.frame.to_csv(self.source, index=False, date_format='%Y-%m-%d')
        return run_etl(self.source, self.db)

    def test_known_metrics_and_repeat_load(self):
        result = self.load()
        self.assertEqual(result['avg_processing_days'], 5.5)
        self.assertEqual(result['backlog_pct'], 50)
        self.assertEqual(result['pending_overdue_count'], 1)
        self.assertEqual(result['resolved_late_count'], 1)
        self.assertEqual(result['resolved_within_target_pct'], 50)
        self.assertEqual(result['revenue_collected_cents'], 10000)
        self.assertEqual(result, self.load())
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM permits').fetchone()[0], 4)
            self.assertEqual(conn.execute('SELECT permit_id FROM bottleneck_applications').fetchone()[0], self.frame.permit_id.iloc[3])
            self.assertEqual(conn.execute('SELECT decisions FROM monthly_throughput').fetchone()[0], 2)
            self.assertAlmostEqual(conn.execute('SELECT sum(revenue_share_pct) FROM category_kpis').fetchone()[0], 100)

    def test_empty_denominators(self):
        self.frame['status_code'] = 'PENDING'
        self.frame['approval_date'] = pd.NaT
        self.frame['rejection_date'] = pd.NaT
        self.frame['collected_fee_cents'] = 0
        result = self.load()
        self.assertIsNone(result['avg_processing_days'])
        self.assertIsNone(result['resolved_within_target_pct'])
        self.assertEqual(result['backlog_pct'], 100)

    def test_invalid_input_preserves_database(self):
        self.load()
        original = self.db.read_bytes()
        for column, value in [('status_code', 'UNKNOWN'), ('snapshot_date', '2026-09-01'),
                              ('quoted_fee_cents', '-1'), ('is_synthetic', False),
                              ('application_date', 'bad-date')]:
            with self.subTest(column=column):
                broken = self.frame.astype(object).copy()
                broken.loc[0, column] = value
                broken.to_csv(self.source, index=False, date_format='%Y-%m-%d')
                with self.assertRaises(ValueError):
                    run_etl(self.source, self.db)
                self.assertEqual(original, self.db.read_bytes())


if __name__ == '__main__':
    unittest.main()
