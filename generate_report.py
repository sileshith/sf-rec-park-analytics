"""Build a thirteen-page portfolio report from SQLite with linked contents.

Install requirements-report.txt, then run python generate_report.py.
All results are read from the database on each build. Fixed page templates keep
opening pages consistent with the supplied visual reference. Text/table layout
raises on overflow instead of silently clipping. No report claims real outcomes.
"""
from __future__ import annotations
import argparse
from datetime import date
from html import escape
from pathlib import Path
import sqlite3

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle

from appendix_data import facilities_frame, SOURCE_URL, RETRIEVED_DATE

ROOT = Path(__file__).resolve().parent
W, H = 595.28, 841.89  # A4
LEFT, WIDTH = 50, W - 100
NAVY = colors.HexColor('#213e89')
BLUE = colors.HexColor('#2861e8')
INK = colors.HexColor('#172033')
PALE = colors.HexColor('#f2f5f9')
GRAY = colors.HexColor('#596d88')
BODY = ParagraphStyle('Body', fontName='Times-Roman', fontSize=11, leading=15, textColor=INK)
SMALL = ParagraphStyle('Small', parent=BODY, fontSize=9, leading=12)
TOTAL_PAGES = 13
LIVE_APP_URL = 'https://sf-rec-park-analytics.streamlit.app/'
GITHUB_URL = 'https://github.com/sileshith/sf-rec-park-analytics'
SCREENSHOT_DATE = '2026-10-23'
VISUALS = [
    ('Executive Summary', 'executive-summary.png', 'visual-executive',
     'The executive view summarizes the full synthetic snapshot, with all category, zone, and status filters selected.',
     'Read resolved turnaround separately from pending age. The revenue figure is modeled collection on approval, not an observed department receipt. Backlog is rounded to two decimals on screen; the precise full-snapshot value is 1.325%.'),
    ('Throughput & Bottlenecks', 'throughput-bottlenecks.png', 'visual-throughput',
     'The category comparison shows completed turnaround alongside pending age. All four synthetic permit categories are included.',
     'Longer special-event reviews are a generator assumption. This comparison is descriptive of modeled records. The active queue below the chart flags pending records strictly past their assumed category targets.'),
    ('Permit Explorer', 'permit-explorer.png', 'visual-explorer',
     'The record explorer shows the full 12,000-record selection with an empty ID search and the overdue-only toggle off.',
     'Application dates define the selected cohort. Recent records at the snapshot can remain pending, with blank decision fields. Search and sorting affect the explorer and its CSV export, while the sidebar filters affect all analysis tabs.'),
    ('Facility Demand Map', 'facility-demand.png', 'visual-map',
     'The map displays assigned synthetic permit counts at authentic DataSF property coordinates. All sidebar filters are selected.',
     'Bubble area represents assigned count. Colors identify invented analytical zones, not official districts. The stable allocation is not evidence of real bookings, category eligibility, capacity, or utilization. Basemap attribution: OpenStreetMap contributors.'),
]
CONTENTS = [
    ('Abstract', 'abstract', 2), ('Motivation and urban context', 'motivation', 3),
    ('Problem statement', 'problem', 3), ('Methodology and architecture', 'method', 4),
    ('Results: synthetic operational performance', 'results', 5),
    ('SLA framework and metric definitions', 'sla', 6),
    ('Limitations', 'limitations', 7), ('Conclusions', 'conclusions', 7),
    ('Recommendations', 'recommendations', 7), ('Appendix: facility reference', 'appendix', 8),
    ('Sources, deployment and reproducibility', 'sources', 9),
    ('Visual appendix: executive summary', 'visual-executive', 10),
    ('Visual appendix: throughput and bottlenecks', 'visual-throughput', 11),
    ('Visual appendix: permit explorer', 'visual-explorer', 12),
    ('Visual appendix: facility demand map', 'visual-map', 13),
]


def snapshot(path):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        con.execute('BEGIN')
        meta = dict(con.execute('SELECT key, value FROM etl_metadata').fetchall())
        if meta.get('schema_version') != '1' or meta.get('synthetic') != 'true':
            raise ValueError('Expected version 1 synthetic database')
        kpi = dict(con.execute('SELECT * FROM executive_kpis').fetchone())
        groups = [dict(row) for row in con.execute('SELECT * FROM category_kpis ORDER BY avg_processing_days DESC')]
        zones = [dict(row) for row in con.execute('SELECT * FROM zone_kpis ORDER BY district_zone')]
        targets = [tuple(row) for row in con.execute('SELECT permit_category, MIN(service_target_days), MAX(service_target_days) FROM permits GROUP BY permit_category')]
    if not kpi['total_permits']:
        raise ValueError('Cannot report an empty snapshot')
    return meta, kpi, groups, zones, targets


def fmt(value, digits=2):
    return 'N/A' if value is None else f'{value:,.{digits}f}'


class Report:
    def __init__(self, output, author, report_date):
        self.c = canvas.Canvas(str(output), pagesize=(W, H), pageCompression=1)
        self.c.setTitle('SF Rec Park Permits & Reservations Analytics Engine')
        self.c.setAuthor(author)
        self.c.setSubject('Independent synthetic-data municipal analytics portfolio')
        self.author, self.report_date = author, report_date
        self.y = H - 56

    def paragraph(self, text, style=BODY, width=WIDTH, x=LEFT, gap=12):
        item = Paragraph(text, style)
        _, height = item.wrap(width, H)
        if self.y - height < 64:
            raise ValueError(f'Report overflow on page {self.c.getPageNumber()}: {text[:60]}')
        item.drawOn(self.c, x, self.y - height)
        self.y -= height + gap

    def heading(self, text, anchor=None):
        if anchor:
            self.c.bookmarkPage(anchor)
            self.c.addOutlineEntry(text, anchor, level=0, closed=False)
        self.paragraph(escape(text), ParagraphStyle('Heading', fontName='Times-Bold', fontSize=16, leading=20, textColor=NAVY), gap=5)
        self.c.setStrokeColor(colors.HexColor('#d1daea'))
        self.c.line(LEFT, self.y, W - LEFT, self.y)
        self.y -= 14

    def table(self, rows, widths, small=False):
        style = SMALL if small else BODY
        data = [[Paragraph(escape(str(value)), style) for value in row] for row in rows]
        table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e6edf8')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PALE]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, 0), (-1, 0), .5, colors.HexColor('#bdcce3')),
        ]))
        _, height = table.wrap(WIDTH, H)
        if self.y - height < 64:
            raise ValueError(f'Table overflow on page {self.c.getPageNumber()}')
        table.drawOn(self.c, LEFT, self.y - height)
        self.y -= height + 16

    def cards(self, cards):
        width = (WIDTH - 16) / 3
        y = self.y - 58
        for index, (value, label) in enumerate(cards):
            x = LEFT + index * (width + 8)
            self.c.setFillColor(PALE)
            self.c.setStrokeColor(colors.HexColor('#c9d5e9'))
            self.c.roundRect(x, y, width, 58, 3, fill=1, stroke=1)
            self.c.setFillColor(NAVY)
            self.c.setFont('Times-Bold', 17)
            self.c.drawCentredString(x + width / 2, y + 32, value)
            self.c.setFont('Times-Roman', 9)
            self.c.drawCentredString(x + width / 2, y + 15, label)
        self.y = y - 20

    def screenshot(self, path):
        """Embed the original captured pixels at their aspect ratio, linked to the app."""
        image = ImageReader(str(path))
        width, height = image.getSize()
        rendered_height = WIDTH * height / width
        if self.y - rendered_height < 64:
            raise ValueError('Screenshot would overflow its appendix page')
        bottom = self.y - rendered_height
        self.c.drawImage(image, LEFT, bottom, width=WIDTH, height=rendered_height, mask='auto')
        self.c.setStrokeColor(colors.HexColor('#d1daea'))
        self.c.rect(LEFT, bottom, WIDTH, rendered_height, fill=0, stroke=1)
        self.c.linkURL(LIVE_APP_URL, (LEFT, bottom, LEFT+WIDTH, self.y), relative=0, thickness=0)
        self.y = bottom - 18

    def finish_page(self):
        c = self.c
        c.setStrokeColor(colors.HexColor('#d1daea'))
        c.line(LEFT, 43, W - LEFT, 43)
        c.setFont('Times-Roman', 8)
        c.setFillColor(GRAY)
        c.drawString(LEFT, 29, 'SF Rec Park Permits & Reservations | Independent synthetic-data study')
        c.drawRightString(W - LEFT, 29, f'Page {c.getPageNumber()} of {TOTAL_PAGES}')
        c.showPage()
        self.y = H - 56


def build_report(database, output, author='Sileshi Hirpa', report_date='2026-10-23'):
    meta, k, categories, zones, targets = snapshot(database)
    output.parent.mkdir(parents=True, exist_ok=True)
    r = Report(output, author, report_date)
    c = r.c
    # 1. Reference-inspired cover.
    c.setFillColor(colors.HexColor('#f4f7fa'))
    c.setStrokeColor(NAVY)
    c.setLineWidth(2)
    c.rect(51, 57, W - 102, H - 108, fill=1, stroke=1)
    r.y = 572
    centered = ParagraphStyle('Center', parent=BODY, alignment=1)
    r.paragraph('CITY AND COUNTY OF SAN FRANCISCO<br/>MUNICIPAL PORTFOLIO',
                ParagraphStyle('Label', parent=centered, fontName='Times-Bold', fontSize=11, leading=13, textColor=BLUE), x=65, width=W-130, gap=18)
    r.paragraph('SF Rec Park Permits &amp; Reservations<br/>Analytics Engine',
                ParagraphStyle('Title', parent=centered, fontName='Times-Bold', fontSize=25, leading=29), x=65, width=W-130, gap=18)
    r.paragraph('Operational Pipeline, Throughput Analysis, and Interactive Dashboard<br/>for the 1820 Junior Administrative Analyst Portfolio', centered, x=68, width=W-136, gap=26)
    c.setStrokeColor(BLUE); c.setLineWidth(3); c.line(W/2-30, r.y, W/2+30, r.y)
    r.y -= 43
    r.paragraph(f'<b>Prepared by:</b> {escape(author)}<br/><b>Target department:</b> San Francisco Recreation and Park Department<br/><b>Office:</b> Permits &amp; Reservations<br/><b>Report date:</b> {escape(report_date)}<br/><b>Data snapshot:</b> {meta["snapshot_date"]}',
                ParagraphStyle('Metadata', parent=centered, textColor=GRAY, fontSize=10, leading=16), x=65, width=W-130, gap=20)
    r.paragraph('Independent portfolio study. All permit transactions and operational results are synthetic.<br/>Not an official City report or representation of departmental performance.',
                ParagraphStyle('Disclosure', parent=centered, textColor=GRAY, fontSize=9, leading=12), x=72, width=W-144)
    r.finish_page()
    # 2. Fully linked contents and abstract.
    r.heading('Table of Contents')
    for title, anchor, page in CONTENTS:
        y = r.y
        c.setFont('Times-Bold', 10); c.setFillColor(NAVY)
        c.drawString(LEFT, y, title)
        c.setFont('Times-Roman', 10); c.setFillColor(INK)
        c.drawRightString(W-LEFT, y, f'Page {page}')
        c.linkAbsolute(title, anchor, Rect=(LEFT,y-5,W-LEFT,y+12), thickness=0)
        c.setStrokeColor(colors.HexColor('#d1daea')); c.setLineWidth(.4)
        c.line(LEFT, y-9, W-LEFT, y-9)
        r.y -= 26
    r.y -= 10
    r.heading('Abstract', 'abstract')
    r.paragraph(f'This portfolio demonstrates a reproducible Python, Pandas, SQLite, and Streamlit workflow for municipal permit operations. It models {k["total_permits"]:,} fictional applications as of {meta["snapshot_date"]}, separates completed-case turnaround from pending-case age, and exposes review delays through a filterable dashboard. Authentic DataSF property coordinates provide geographic context, while facility assignments remain simulated.')
    r.paragraph(f'The snapshot yields {fmt(k["avg_processing_days"])} calendar days of average resolved turnaround, {k["pending_permits"]:,} pending applications, and {k["pending_overdue_count"]:,} overdue pending cases under assumed category targets. These outputs demonstrate analytical methods, not measured SF Rec Park operations.')
    r.paragraph('<b>Core objective:</b> Make administrative queue measures explicit, reproducible, and understandable so an analyst can distinguish active backlog from historical late decisions.',
                ParagraphStyle('Callout', parent=BODY, backColor=PALE, borderColor=BLUE, borderWidth=1, borderPadding=10))
    r.finish_page()
    # 3. Motivation and problem, with reference-style KPI tiles.
    r.heading('Project Motivation & Urban Context', 'motivation')
    r.paragraph('The project is motivated by public service engagement and everyday observations of how residents and visitors use San Francisco. Rideshare conversations about neighborhoods, destinations, and access to parks provide a practical starting point for asking how public assets and administrative services support urban life. These observations are motivation, not a representative survey or evidence of permit demand.')
    r.paragraph('For an 1820 Junior Administrative Analyst portfolio, the emphasis is on defensible calculations, data quality, transparent assumptions, and clear operational reporting. The application connects transaction-level records to summaries that can support questions about service delivery, queue monitoring, and workload distribution.')
    r.heading('Problem Statement', 'problem')
    r.paragraph('An analyst needs to distinguish volume from backlog, pending age from completed turnaround, and collected revenue from quoted fees. Mixing those measures can hide active queues or misstate performance. This simulation builds a consistent snapshot that can be validated, queried, filtered, and explained without exposing applicant information.')
    r.cards([(f'{k["total_permits"]:,}', 'Synthetic applications'), (f'{fmt(k["avg_processing_days"])} days', 'Average resolved turnaround'), ('4 zones', 'Invented analytical groupings')])
    r.paragraph('<b>Operational questions:</b> Which categories have longer completed review cycles? Which pending applications exceed their assumed targets? How are modeled fees distributed? How do filters change the interpretation of executive measures?')
    r.paragraph('<b>Interpretation boundary:</b> The tool demonstrates a decision-support workflow. It does not establish actual department delays, staffing requirements, booking eligibility, customer outcomes, or facility utilization.')
    r.finish_page()
    # 4. Architecture.
    r.heading('Methodology & Data Architecture', 'method')
    r.table([['Stage','Implementation','Output'], ['Generate','data_generator.py','Fictional CSV + seed/version manifest'], ['Validate and enrich','etl.py','Cleaned snapshot, dates, durations, flags'], ['Store and aggregate','SQLite','Permits table, indexes, KPI views'], ['Reference and map','appendix_data.py','Sourced property points + simulated assignments'], ['Explore and report','app.py / generate_report.py','Filtered dashboard and this PDF']], [95,150,WIDTH-245], small=True)
    r.paragraph('The generator uses a fixed seed and observation cutoff. Seasonal intake weights, category mix, review-time distributions, fees, approval rates, and analytical zones are declared assumptions. Special events have a deliberately longer review distribution, and the South zone has a modeled lag multiplier. Later comparisons therefore recover design choices rather than independent empirical findings.')
    r.paragraph('The ETL trims text, validates types and required fields, enforces unique synthetic IDs and a single snapshot, and rejects impossible chronology. Approval and rejection dates must agree with status; pending records have no decision date. Revenue follows the explicit full-payment-on-approval assumption. A temporary SQLite build replaces the prior database only after a successful load.')
    r.paragraph('All durations are calendar days. Completed turnaround is decision date minus application date. Pending age is snapshot date minus application date. A bottleneck is a pending case whose age is strictly greater than its category target. Decisions exactly on target are compliant; historical late decisions remain a separate measure.')
    r.paragraph('SQLite views expose executive, category, zone, category-zone, and decision-month summaries. Dashboard filters define application cohorts. The facility layer selects one authentic property within each invented zone using a stable hash of permit ID; it changes neither transaction counts nor revenue.')
    r.finish_page()
    # 5. Computed results.
    r.heading('Results & Synthetic Operational Performance', 'results')
    r.table([['Indicator','Computed result'], ['Total / resolved applications', f'{k["total_permits"]:,} / {k["resolved_permits"]:,}'], ['Approved / rejected', f'{k["approved_permits"]:,} / {k["rejected_permits"]:,}'], ['Average resolved turnaround', f'{fmt(k["avg_processing_days"])} calendar days'], ['Modeled revenue collected', f'${k["revenue_collected_cents"]/100:,.2f}'], ['Pending / backlog percentage', f'{k["pending_permits"]:,} / {fmt(k["backlog_pct"],3)}%'], ['Overdue pending / share of pending', f'{k["pending_overdue_count"]:,} / {fmt(k["pending_overdue_pct"])}%'], ['Historical late decisions', f'{k["resolved_late_count"]:,}'], ['Resolved within assumed target', f'{fmt(k["resolved_within_target_pct"])}%']], [WIDTH*.62,WIDTH*.38], small=True)
    r.paragraph('Category comparison: resolved cases only. Counts and revenue include all statuses in each category.', SMALL, gap=6)
    r.table([['Category','Permits','Avg days','Overdue pending','Revenue (USD)']] +
            [[g['permit_category'], f'{g["total_permits"]:,}', fmt(g['avg_processing_days']), g['pending_overdue_count'], f'${g["revenue_collected_cents"]/100:,.2f}'] for g in categories], [115,55,65,85,WIDTH-320], small=True)
    r.paragraph('Zone comparison: invented analytical groupings, not official department districts.', SMALL, gap=6)
    r.table([['Zone','Permits','Avg resolved days','Overdue pending']] +
            [[g['district_zone'], f'{g["total_permits"]:,}', fmt(g['avg_processing_days']), g['pending_overdue_count']] for g in zones], [90,85,160,WIDTH-335], small=True)
    r.finish_page()
    # 6. SLA.
    r.heading('SLA Framework & Metric Definitions', 'sla')
    r.paragraph('Current baseline: service-category targets measured in calendar days. The database has date-only records and does not model customer profiles, intake acknowledgments, priority escalation, business hours, holidays, or portal availability.')
    r.table([['Permit category','Assumed calendar-day target']] + [[name, low if low == high else f'{low}-{high}'] for name,low,high in targets], [WIDTH*.55,WIDTH*.45], small=True)
    r.paragraph('<b>Backlog percentage:</b> pending / total applications x 100.<br/><b>Overdue pending percentage:</b> overdue pending / pending x 100.<br/><b>Within-target compliance:</b> resolved on or before target / resolved x 100.<br/><b>Revenue:</b> sum of collected integer US cents, divided by 100 for dollars.<br/><b>Undefined measures:</b> empty denominators are NULL / N/A, not zero.')
    r.heading('Proposed Customer-Based Framework')
    r.paragraph('The proposed framework would layer customer-profile differentiation onto a baseline service model. The following user-proposed priorities are future design objectives, not verified SF Rec Park commitments and not implemented as current business-day targets.')
    r.table([['Priority','Initial response','Resolution'], ['P1: special events / urgent','4 business hours','5 business days'], ['P2: athletic fields','24 business hours','10 business days'], ['P3: picnic / general','48 business hours','15 business days']], [WIDTH*.48,WIDTH*.26,WIDTH*.26], small=True)
    r.paragraph('Additional proposed objectives are a 3% backlog ceiling, a 14-day stale threshold, and 99.9% portal uptime. Implementing them requires agreed customer/priority mappings, clubhouse treatment, a holiday and business-hours calendar, response event timestamps, and independent uptime monitoring. A priority label alone is not customer-based governance.')
    r.finish_page()
    # 7. Limitations and action recommendations.
    r.heading('Limitations', 'limitations')
    r.paragraph('1. Synthetic parameters are not calibrated to actual operations. No inference about real staffing, fees, bottlenecks, customer groups, or service quality is supported.<br/>2. Pending cases are right-censored at the snapshot. Resolved-only turnaround can understate eventual processing time for recent cohorts.<br/>3. Revenue assumes full collection on approval and omits refunds, waivers, partial payment, and accounting adjustments.<br/>4. Facility assignment is illustrative and does not validate permit eligibility, available amenities, capacity, occupancy, or actual demand. The 19 reference sites are a curated subset.<br/>5. The project does not establish legal restrictions on all transaction records. Availability and disclosure rules require field-specific source verification.<br/>6. No business-day response compliance, uptime, causal impact, or forecast accuracy is measured.')
    r.heading('Conclusions', 'conclusions')
    r.paragraph(f'The completed workflow reconciles {k["total_permits"]:,} synthetic transactions across CSV, SQLite, dashboard summaries, and facility demand totals. It distinguishes {k["pending_overdue_count"]:,} actionable overdue pending records from {k["resolved_late_count"]:,} historical late decisions. Its portfolio value is a reproducible, auditable method for operational analysis, not evidence of an actual departmental performance gap.')
    r.heading('Recommendations', 'recommendations')
    r.paragraph('<b>Standardize intake:</b> Pilot document checklists and consistent acknowledgment events. Measure completeness and follow-up rates before proposing a quantified benefit.<br/><b>Review the active queue:</b> Use overdue age and case context to support staff triage. Do not infer urgency or regulatory complexity from elapsed days alone.<br/><b>Define governance:</b> Agree on service targets, customer tiers, business calendars, exception rules, metric owners, and a reporting cadence before operational adoption.<br/><b>Evaluate capacity carefully:</b> Gather actual reservation slots, closures, amenities, and occupancy before recommending dynamic facility or staffing allocation.<br/><b>Validate with a baseline:</b> Compare a small pilot against documented outcomes. No 20% reduction or other causal gain is claimed by this simulation.')
    r.finish_page()
    # 8. Complete facility appendix.
    r.heading('Appendix: Authentic Facility Reference', 'appendix')
    r.paragraph('Curated DataSF properties. Names, IDs and coordinates are source fields. Analytical zones are invented; points represent properties, not reservable entrances. Golden Gate Park retains its seven source sections.', SMALL)
    facilities = facilities_frame()
    rows = [['Property ID / source name','Latitude','Longitude','Modeled zone']]
    for _, site in facilities.iterrows():
        rows.append([f'{site.source_property_id}: {site.facility_name}', f'{site.latitude:.6f}', f'{site.longitude:.6f}', site.district_zone])
    r.table(rows, [245,75,85,WIDTH-405], small=True)
    r.paragraph(f'Source: <link href="{SOURCE_URL}" color="#213e89">DataSF Recreation and Parks Properties (gtr9-ntp6)</link>. Retrieved {RETRIEVED_DATE}. Source precision is preserved in the bundled CSV; coordinates above are rounded to six decimals.', SMALL)
    r.paragraph(f'Explore the deployed facility map in the <link href="{LIVE_APP_URL}" color="#213e89">live dashboard</link>; source records and allocation code are in the <link href="{GITHUB_URL}" color="#213e89">public GitHub repository</link>. The visual appendix begins on page 10.', SMALL)
    r.finish_page()
    # 9. Provenance and reproducibility.
    r.heading('Sources, Deployment & Reproducibility', 'sources')
    r.paragraph(f'<b>Live dashboard:</b> <link href="{LIVE_APP_URL}" color="#213e89">{LIVE_APP_URL}</link><br/><b>Public source repository:</b> <link href="{GITHUB_URL}" color="#213e89">{GITHUB_URL}</link><br/>Public access and deployed views verified on {SCREENSHOT_DATE}.')
    r.paragraph(f'<b>Public reference data:</b> <link href="{SOURCE_URL}" color="#213e89">DataSF Recreation and Parks Properties</link>. The inventory describes land owned and/or maintained by the department. A 19-record excerpt is preserved with the retrieval date and full-download hash. The catalog lists PDDL 1.0 for the source data; repository code is MIT licensed.')
    r.paragraph('<link href="https://catalog.data.gov/dataset/recreation-and-parks-properties" color="#213e89">Data.gov catalog and source metadata</link><br/><link href="https://opendatacommons.org/licenses/pddl/1-0/" color="#213e89">Public Domain Dedication and License 1.0</link><br/><link href="https://docs.streamlit.io/" color="#213e89">Streamlit documentation</link><br/><link href="https://docs.reportlab.com/" color="#213e89">ReportLab documentation</link>')
    r.paragraph('<b>Transaction provenance:</b> data/permits.manifest.json records generator parameters and NumPy/Pandas versions. For exact synthetic regeneration, use those recorded versions. Application dependency ranges permit updates; the committed CSV and database are the stable portfolio snapshot.')
    r.paragraph(f'<b>Database provenance:</b> schema version {meta["schema_version"]}; snapshot {meta["snapshot_date"]}; source CSV SHA-256:', gap=6)
    r.paragraph(meta['source_sha256'], ParagraphStyle('Hash', fontName='Courier', fontSize=8, leading=11), gap=18)
    r.paragraph('<b>Rebuild from repository root:</b><br/>1. Install requirements.txt and requirements-report.txt.<br/>2. Run python etl.py to validate and rebuild SQLite from the committed CSV.<br/>3. Run python -m unittest discover -s tests -v.<br/>4. Run python generate_report.py.<br/>5. Run streamlit run app.py to inspect the same snapshot.')
    r.paragraph('<b>Dashboard coverage:</b> Executive summary; throughput and bottlenecks; filterable record explorer; illustrative facility demand map; SLA framework and definitions. Filters use application dates and apply to all analysis tabs. Map tiles require internet; SQLite and reference tables are local.')
    r.paragraph('<b>Deployment status:</b> The dashboard is publicly deployed on Streamlit Community Cloud from main / app.py using Python 3.11. The bundled SQLite snapshot loads without a cloud ETL job. GitHub Actions has passed on Python 3.11 and 3.12, including the report build. Docker configurations remain available but container execution has not been verified. Inactive cloud apps may require a short wake-up period.')
    r.finish_page()
    # 10-13. Fresh captures of the deployed public dashboard.
    for number, (title, filename, anchor, caption, guide) in enumerate(VISUALS, 1):
        r.heading(f'Visual Appendix {number}: {title}', anchor)
        r.paragraph(f'Captured from the public deployment on {SCREENSHOT_DATE}. All permit records are synthetic.', SMALL)
        r.screenshot(ROOT/'assets/screenshots/deployed'/filename)
        r.paragraph(f'<b>Figure {number}.</b> {caption}')
        r.heading('How to read this view')
        r.paragraph(guide)
        r.paragraph(f'<b>Live view:</b> <link href="{LIVE_APP_URL}" color="#213e89">{LIVE_APP_URL}</link><br/><b>Source and reproducibility:</b> <link href="{GITHUB_URL}" color="#213e89">GitHub repository</link>', SMALL)
        r.paragraph(f'Original image: assets/screenshots/deployed/{filename}. Capture provenance and SHA-256 values are recorded in capture_manifest.json in that directory. Click the screenshot to open the live application.', SMALL)
        r.finish_page()
    c.save()
    return k


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT/'data/permits.sqlite')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/sf_rec_park_project_report.pdf')
    parser.add_argument('--author', default='Sileshi Hirpa')
    parser.add_argument('--date', default='2026-10-23', help='ISO report date, independent of host timezone')
    args = parser.parse_args()
    date.fromisoformat(args.date)
    build_report(args.database, args.output, args.author, args.date)
    print(f'Built {TOTAL_PAGES}-page report: {args.output}')


if __name__ == '__main__':
    main()
