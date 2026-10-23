"""Verify report results, internal navigation, and facility appendix coverage."""
from pathlib import Path
import tempfile
import unittest
from pypdf import PdfReader
from generate_report import build_report, ROOT, CONTENTS, snapshot, TOTAL_PAGES, LIVE_APP_URL, GITHUB_URL
from appendix_data import facilities_frame


class ReportTests(unittest.TestCase):
    def test_report_links_and_results(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.pdf'
            build_report(ROOT/'data/permits.sqlite', path)
            reader = PdfReader(path)
            self.assertEqual(len(reader.pages), TOTAL_PAGES)
            self.assertEqual(len(reader.outline), len(CONTENTS))
            links = reader.pages[1]['/Annots']
            self.assertEqual(len(links), len(CONTENTS))
            for link, (_, _, page) in zip(links, CONTENTS):
                destination = link.get_object()['/Dest'][0].get_object()
                self.assertEqual(reader.get_page_number(destination) + 1, page)
            _, kpi, _, _, _ = snapshot(ROOT/'data/permits.sqlite')
            results = reader.pages[4].extract_text()
            for value in [f'{kpi["total_permits"]:,}', f'{kpi["avg_processing_days"]:.2f}',
                          f'${kpi["revenue_collected_cents"]/100:,.2f}', f'{kpi["pending_overdue_count"]:,}']:
                self.assertIn(value, results)
            links = [annotation.get_object().get('/A', {}).get('/URI')
                     for page in reader.pages for annotation in page.get('/Annots', [])]
            self.assertIn(LIVE_APP_URL, links)
            self.assertIn(GITHUB_URL, links)
            for page in reader.pages[9:]:
                self.assertGreater(len(page.images), 0)
                self.assertIn('Captured from the public deployment', page.extract_text())
            self.assertNotIn('public hosting remains a publication step', reader.pages[8].extract_text())
            appendix = reader.pages[7].extract_text()
            for name in facilities_frame().facility_name:
                self.assertIn(name, appendix)
            for number, page in enumerate(reader.pages, 1):
                self.assertIn(f'Page {number} of {TOTAL_PAGES}', page.extract_text())


if __name__ == '__main__':
    unittest.main()
