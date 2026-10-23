"""Dashboard integration checks: python -m unittest -v test_app.py."""
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from appendix_data import attach_facilities, facilities_frame, facility_demand
from app import DB_PATH, calculate_kpis, filter_permits, load_snapshot

APP = Path(__file__).resolve().parents[1] / 'app.py'


class DashboardTests(unittest.TestCase):
    def test_kpis_match_sqlite(self):
        df, _ = load_snapshot(DB_PATH)
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            expected = dict(conn.execute('SELECT * FROM executive_kpis').fetchone())
        actual = calculate_kpis(df)
        self.assertEqual(actual['total'], expected['total_permits'])
        self.assertAlmostEqual(actual['avg_days'], expected['avg_processing_days'])
        self.assertAlmostEqual(actual['backlog_pct'], expected['backlog_pct'])
        self.assertAlmostEqual(actual['revenue'], expected['revenue_collected_cents'] / 100)
        self.assertEqual(actual['overdue'], expected['pending_overdue_count'])

    def test_filters_are_inclusive(self):
        df, _ = load_snapshot(DB_PATH)
        day = df.application_date.max().date()
        subset = filter_permits(df, (day, day), ['Picnic Area'], ['East'], ['PENDING'])
        self.assertTrue((subset.application_date.dt.date == day).all())
        self.assertTrue(subset.permit_category.eq('Picnic Area').all())
        self.assertTrue(subset.district_zone.eq('East').all())
        self.assertTrue(subset.status_code.eq('PENDING').all())
        self.assertTrue(filter_permits(df, (day, day), [], [], []).empty)

    def test_ui_filters_and_search(self):
        app = AppTest.from_file(str(APP)).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.tabs), 5)
        self.assertTrue(any('12,000' in item.value and 'metric-value' in item.value for item in app.markdown))
        app.sidebar.multiselect[2].set_value(['PENDING']).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, '159')
        self.assertTrue(any('N/A' in item.value and 'metric-value' in item.value for item in app.markdown))
        self.assertTrue(any('100.00%' in item.value for item in app.markdown))
        app.text_input[0].set_value('NO-MATCH').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('No matching permit ID found' in item.value for item in app.warning))
        self.assertFalse(any(getattr(item, 'key', None) == 'explorer' for item in app.get('download_button')))
        app.sidebar.multiselect[0].set_value([]).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, '0')
        self.assertTrue(any('N/A' in item.value and 'metric-value' in item.value for item in app.markdown))

    def test_reference_and_demand(self):
        reference = facilities_frame()
        self.assertEqual(len(reference), 19)
        self.assertTrue(reference.facility_id.is_unique)
        self.assertTrue(reference.latitude.between(37.70, 37.82).all())
        self.assertTrue(reference.longitude.between(-122.52, -122.37).all())
        df, _ = load_snapshot(DB_PATH)
        demand = facility_demand(df)
        self.assertEqual(demand.permit_count.sum(), len(df))
        self.assertEqual(demand.overdue_pending.sum(), df.pending_overdue.sum())
        self.assertEqual(demand.collected_fee_cents.sum(), df.collected_fee_cents.sum())
        raw = df.drop(columns=list(reference.columns.intersection(df.columns).difference(['district_zone'])))
        reassigned = attach_facilities(raw.sample(frac=1, random_state=7)).set_index('permit_id').facility_id.sort_index()
        self.assertTrue(reassigned.equals(df.set_index('permit_id').facility_id.sort_index()))
        self.assertEqual(facility_demand(df.iloc[:0]).permit_count.sum(), 0)

    def test_missing_database_has_setup_message(self):
        with patch.dict('os.environ', {'PERMITS_DATABASE': str(APP.parent / 'missing.sqlite')}):
            app = AppTest.from_file(str(APP)).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertIn('python etl.py', app.code[0].value)


if __name__ == '__main__':
    unittest.main()
