"""Read-only synthetic permit dashboard. Launch: streamlit run app.py."""
from pathlib import Path
import os
import sqlite3
from html import escape

import pandas as pd
import streamlit as st
import plotly.express as px

from appendix_data import attach_facilities, facility_demand, facilities_frame, SOURCE_URL, RETRIEVED_DATE

DB_PATH = Path(os.environ.get('PERMITS_DATABASE', str(Path(__file__).parent / 'data/permits.sqlite')))


def load_snapshot(path: Path) -> tuple[pd.DataFrame, dict]:
    """Read a consistent SQLite snapshot without creating or modifying a database."""
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.execute('BEGIN')
        metadata = dict(conn.execute('SELECT key, value FROM etl_metadata'))
        if metadata.get('schema_version') != '1' or metadata.get('synthetic') != 'true':
            raise ValueError('Expected schema version 1 synthetic data. Run etl.py.')
        frame = pd.read_sql_query('SELECT * FROM permits', conn,
                                 parse_dates=['application_date', 'decision_date', 'snapshot_date'])
    if frame.empty:
        raise ValueError('The database contains no permits. Run the generator and ETL.')
    return attach_facilities(frame), metadata


def filter_permits(df, dates, categories, zones, statuses):
    """Apply inclusive application-date and explicit selection filters."""
    return df.loc[
        df.application_date.between(pd.Timestamp(dates[0]), pd.Timestamp(dates[1]))
        & df.permit_category.isin(categories) & df.district_zone.isin(zones)
        & df.status_code.isin(statuses)
    ].copy()


def calculate_kpis(df):
    """Recalculate metrics for the selected cohort using the ETL definitions."""
    pending = df.status_code.eq('PENDING')
    resolved = ~pending
    return {
        'total': len(df), 'avg_days': df.processing_days.mean(),
        'revenue': df.collected_fee_cents.sum() / 100,
        'backlog_pct': 100 * pending.mean() if len(df) else float('nan'),
        'pending': int(pending.sum()), 'overdue': int(df.pending_overdue.sum()),
        'within_pct': 100 * (1 - df.loc[resolved, 'resolved_late'].mean()),
    }


def display_number(value, suffix=''):
    return 'N/A' if pd.isna(value) else f'{value:,.2f}{suffix}'


def record_table(df, key):
    """Render auditable records and export the entire current selection."""
    display = df.copy()
    for name in ('application_date', 'decision_date', 'snapshot_date'):
        display[name] = display[name].dt.strftime('%Y-%m-%d')
    st.dataframe(display, hide_index=True, width='stretch')
    st.download_button('Download these records (CSV)', display.to_csv(index=False).encode('utf-8'),
                       file_name=f'synthetic_permits_{key}.csv', mime='text/csv', key=key)


def metric_card(label, value, icon, accent=''):
    """Responsive icon card: preserve full currency precision without ellipsis."""
    st.markdown(f'<div class="metric-card {accent}"><div class="metric-icon" aria-hidden="true">{icon}</div>'
                f'<div class="metric-title">{escape(label)}</div>'
                f'<div class="metric-value">{escape(value)}</div></div>', unsafe_allow_html=True)


def draw_chart(fig, key):
    """Use consistent chart padding and automatic axis-label margins."""
    fig.update_layout(margin=dict(t=30, b=30, l=30, r=30), legend_title_text='',
                      font=dict(color='#334155'), paper_bgcolor='rgba(0,0,0,0)')
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True, rangemode='tozero')
    st.plotly_chart(fig, width='stretch', key=key, config={'scrollZoom': False})


def main():
    st.set_page_config(page_title='SF Rec Park | Permits Analytics', page_icon='🌳', layout='wide')
    st.markdown('''<style>
    .metric-card {background:#fff; padding:18px 12px; border-radius:12px;
      border:1px solid #dce3ef; border-top:5px solid #2454a6;
      box-shadow:0 4px 10px #142b4910; text-align:center; margin-bottom:12px;
      container-type:inline-size; color:#243449;}
    .metric-card.warning {border-top-color:#d97816;}
    .metric-card.success {border-top-color:#23834a;}
    .metric-icon {font-size:1.8rem; margin-bottom:6px;}
    .metric-title {font-size:.78rem; font-weight:600; min-height:2.4em;
      text-transform:uppercase; letter-spacing:.04em; color:#495970;}
    .metric-value {font-size:clamp(.75rem,8cqw,1.65rem); font-weight:750;
      margin-top:8px; white-space:nowrap; font-variant-numeric:tabular-nums;}
    h1,h2,h3 {color:#193c74;}
    </style>''', unsafe_allow_html=True)
    st.caption('Municipal Operations & Public Sector Portfolio')
    st.title('SF Rec Park Permits & Reservations')
    st.write('Explore modeled service delivery, review queues, and permit demand.')
    st.info('Synthetic data demonstration. Zones, fees, and service targets are modeling assumptions, not official SF Rec Park policy or performance.')
    try:
        df, metadata = load_snapshot(DB_PATH)
    except (OSError, sqlite3.Error, ValueError, KeyError) as error:
        st.error(f'Unable to load the permit snapshot: {error}')
        st.code('python data_generator.py\npython etl.py\nstreamlit run app.py', language='bash')
        st.stop()
    st.caption(f"Snapshot: {metadata['snapshot_date']} • {len(df):,} permits • Calendar-day model")
    with st.sidebar:
        st.header('Filter permits')
        st.caption('Filters apply to all analysis tabs. Dates refer to applications, not decisions.')
        dates = st.date_input('Application date range',
                              value=(df.application_date.min().date(), df.application_date.max().date()),
                              min_value=df.application_date.min().date(), max_value=df.application_date.max().date())
        categories = st.multiselect('Permit category', sorted(df.permit_category.unique()), default=sorted(df.permit_category.unique()))
        zones = st.multiselect('Analytical zone', sorted(df.district_zone.unique()), default=sorted(df.district_zone.unique()))
        statuses = st.multiselect('Status', sorted(df.status_code.unique()), default=sorted(df.status_code.unique()))
        st.button('Refresh database')  # Each rerun opens a new read-only snapshot; no stale cache.
    if len(dates) != 2:
        st.warning('Choose both a start and end date to continue.')
        st.stop()
    selected = filter_permits(df, dates, categories, zones, statuses)
    st.caption(f'{len(selected):,} of {len(df):,} permits selected')
    executive, bottlenecks, explorer, geospatial, framework = st.tabs([
        'Executive summary', 'Throughput & bottlenecks', 'Permit explorer', 'Facility demand map', 'SLA framework & definitions'])
    with executive:
        if selected.empty:
            st.warning('No permits match these filters. Expand the selections in the sidebar.')
        kpi = calculate_kpis(selected)
        columns = st.columns(4)
        for column, label, value, icon, accent in zip(columns,
            ['Permit volume', 'Average resolved turnaround', 'Modeled revenue collected', 'Pending backlog'],
            [f"{kpi['total']:,}", display_number(kpi['avg_days'], ' days'), f"${kpi['revenue']:,.2f}", display_number(kpi['backlog_pct'], '%')],
            ['📋', '⏱️', '💰', '⚠️'], ['', 'success', 'success', 'warning']):
            with column:
                metric_card(label, value, icon, accent)
        st.caption('Turnaround excludes pending cases. Revenue is assumed collected in full on approval. All KPIs reflect the selected cohort.')
        a, b, c = st.columns(3)
        a.metric('Pending permits', kpi['pending'])
        b.metric('Overdue pending permits', kpi['overdue'])
        c.metric('Resolved within assumed target', display_number(kpi['within_pct'], '%'))
        if not selected.empty:
            left, right = st.columns(2)
            with left:
                st.subheader('Permit status')
                status_counts = selected.status_code.value_counts().rename_axis('Status').reset_index(name='Permits')
                fig = px.bar(status_counts, x='Status', y='Permits', color='Status',
                             color_discrete_sequence=['#2454a6', '#23834a', '#d97816'])
                fig.update_yaxes(range=[0, max(1, status_counts.Permits.max() * 1.12)], rangemode='tozero')
                draw_chart(fig, 'status_chart')
            with right:
                st.subheader('Collected revenue by category (USD)')
                revenue = (selected.groupby('permit_category').collected_fee_cents.sum() / 100).rename('USD').reset_index()
                draw_chart(px.bar(revenue, x='permit_category', y='USD', labels={'permit_category':'Permit category'},
                                  color_discrete_sequence=['#23834a']), 'revenue_chart')
            st.subheader('Decisions over time')
            resolved = selected.dropna(subset=['decision_date']).copy()
            if resolved.empty:
                st.info('No resolved cases in the selected cohort.')
            else:
                monthly = resolved.groupby([resolved.decision_date.dt.to_period('M').astype(str), 'status_code']).size().unstack(fill_value=0)
                draw_chart(px.line(monthly, labels={'value':'Decisions', 'decision_date':'Decision month', 'status_code':'Status'}), 'throughput_chart')
            st.caption('Monthly decisions belong to the selected application cohort; this is not an unfiltered office throughput total.')
    with bottlenecks:
        st.subheader('Where are reviews taking longer?')
        st.caption('Resolved turnaround and pending age are separate measures. A bottleneck is pending age strictly greater than its category target.')
        dimension = st.selectbox('Compare by', ['permit_category', 'district_zone'], format_func=lambda x: x.replace('_', ' ').title())
        if selected.empty:
            st.info('No records to compare.')
        else:
            grouped = selected.groupby(dimension).agg(
                permits=('permit_id', 'size'), avg_processing_days=('processing_days', 'mean'),
                avg_pending_age_days=('pending_age_days', 'mean'), overdue_pending=('pending_overdue', 'sum'),
                resolved_late=('resolved_late', 'sum'))
            comparison = grouped[['avg_processing_days', 'avg_pending_age_days']].rename(columns={
                'avg_processing_days':'Resolved turnaround', 'avg_pending_age_days':'Pending age'})
            draw_chart(px.bar(comparison, barmode='group', labels={'value':'Calendar days', 'variable':'Measure',
                       dimension:dimension.replace('_', ' ').title()}), 'review_chart')
            st.dataframe(grouped, width='stretch')
        st.subheader('Active bottleneck queue')
        overdue = selected.loc[selected.bottleneck_flag.eq(1)].sort_values(['days_over_target', 'permit_id'], ascending=[False, True])
        if overdue.empty:
            st.success('No overdue pending cases in this selection.')
        record_table(overdue, 'bottlenecks')
        st.caption('Longer review cycles are built into the synthetic generator; these are not findings about actual department operations.')
    with explorer:
        st.subheader('Explore permit records')
        query = st.text_input('Search permit ID', placeholder='SYN-0000123')
        records = selected.loc[selected.permit_id.str.contains(query.strip(), case=False, regex=False)]
        overdue_only = st.checkbox('Show overdue pending only')
        if overdue_only:
            records = records.loc[records.bottleneck_flag.eq(1)]
        order = st.selectbox('Sort records by', ['application_date', 'days_over_target', 'permit_id'])
        records = records.sort_values(order, ascending=order == 'permit_id')
        st.caption(f'{len(records):,} matching records. Search and overdue-only controls affect this explorer and its download only.')
        if records.empty:
            if query.strip():
                st.warning("No matching permit ID found. Please check your search query.")
                st.caption('The search applies within the current sidebar and overdue-only filters.')
            else:
                st.info('No permits match the current filters.')
        else:
            record_table(records, 'explorer')
    with geospatial:
        st.subheader('Illustrative facility demand across San Francisco')
        st.info('Real property locations · Synthetic permit allocation. Counts do not represent observed bookings, utilization, capacity, or reservable amenities.')
        st.caption('Each permit is assigned reproducibly to one reference property within its invented zone. Assignment is illustrative and does not verify permit-category eligibility. The map uses all sidebar filters.')
        demand = facility_demand(selected)
        metric = st.radio('Map measure', ['permit_count', 'overdue_pending'],
                          format_func=lambda name: {'permit_count':'Assigned synthetic permits', 'overdue_pending':'Overdue pending permits'}[name], horizontal=True)
        active = demand.loc[demand[metric] > 0].copy()
        if active.empty:
            st.info('No mapped demand for this selection and measure.')
        else:
            fig = px.scatter_map(active, lat='latitude', lon='longitude', size=metric,
                color='district_zone', hover_name='facility_name', size_max=36, zoom=10.4,
                center={'lat':37.76, 'lon':-122.445}, map_style='open-street-map',
                hover_data={'permit_count':True, 'overdue_pending':True, 'latitude':False, 'longitude':False},
                labels={'district_zone':'Modeled zone', 'permit_count':'Assigned permits', 'overdue_pending':'Overdue pending'})
            fig.update_layout(height=540)
            draw_chart(fig, 'facility_map')
        st.caption('Bubble area scales with count. Zero-count sites remain in the table. Basemap tiles require internet access; reference data is bundled locally.')
        st.dataframe(demand[['facility_name', 'district_zone', 'permit_count', 'overdue_pending', 'latitude', 'longitude']], hide_index=True, width='stretch')
        st.download_button('Download facility demand (CSV)', demand.to_csv(index=False).encode('utf-8'),
                           file_name='synthetic_facility_demand.csv', mime='text/csv')
        st.markdown(f'Location source: [DataSF Recreation and Parks Properties]({SOURCE_URL}) · Retrieved {RETRIEVED_DATE}.')
        st.caption('Curated subset of 19 properties. Golden Gate Park is shown in its seven inventory sections. Source points are property reference locations, not entrances. Zone labels are portfolio assumptions.')
        with st.expander('Facility reference appendix'):
            st.dataframe(facilities_frame(), hide_index=True, width='stretch')
    with framework:
        st.subheader('Measured today: category-based calendar-day targets')
        st.write('The current model sets targets by permit category. It has no applicant-profile tiers, intake acknowledgment timestamps, holiday calendar, or portal monitoring data.')
        st.dataframe(df.groupby('permit_category').service_target_days.first().rename('Assumed target (calendar days)'), width='stretch')
        st.write('Backlog = pending ÷ selected permits. Within-target compliance = resolved on or before target ÷ resolved permits. Missing denominators display N/A. A case exactly at its target is not overdue.')
        st.subheader('Proposed customer-based framework')
        st.caption('User-proposed design for future implementation; not a verified departmental SLA. Priority alone does not implement customer-based differentiation.')
        st.table(pd.DataFrame({
            'Priority': ['P1: special events / urgent', 'P2: athletic fields', 'P3: picnic / general'],
            'Initial response objective': ['4 business hours', '24 business hours', '48 business hours'],
            'Resolution objective': ['5 business days', '10 business days', '15 business days']}))
        st.write('The proposal also includes a 3% backlog ceiling, a 14-day stale threshold, and 99.9% portal uptime. These are not used to replace the current model targets. Clubhouse priority, urgency rules, customer profiles, holidays, business hours, and a stale-day convention must be defined before implementation.')
        st.write('Business-day resolution requires an agreed working calendar; intake response needs timestamps and an acknowledgment event; uptime needs independent availability observations. None can be inferred from the current date-only dataset.')
        st.caption('Permit counts measure modeled demand, not occupancy or actual facility utilization. Four analytical zones are invented groupings, not official districts.')
        with st.expander('Data provenance'):
            st.json(metadata)


if __name__ == '__main__':
    main()
