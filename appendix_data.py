"""Authentic DataSF property points with explicitly modeled demand allocation.

Source: Recreation and Parks Properties, DataSF gtr9-ntp6.
Retrieved 2026-10-23. Names, IDs, addresses and point coordinates are copied
from the public inventory; four-zone assignments are portfolio assumptions.
Points represent properties, not reservable subfacilities or entrances.
"""
from hashlib import sha256
import pandas as pd

SOURCE_URL = 'https://data.sf.gov/d/gtr9-ntp6'
SOURCE_API = 'https://data.sf.gov/resource/gtr9-ntp6.json'
RETRIEVED_DATE = '2026-10-23'
ALLOCATION_VERSION = 'zone-sha256-v1'
FACILITIES = ({'facility_id': 'RPD-112',
  'source_property_id': '112',
  'facility_name': 'Yacht Harbor and Marina Green',
  'latitude': 37.80796275,
  'longitude': -122.44119806,
  'property_type': 'Regional Park',
  'address': '1 Marina Green Dr',
  'district_zone': 'North',
  'source_data_as_of': '2025-12-18T09:03:43.000'},
 {'facility_id': 'RPD-125',
  'source_property_id': '125',
  'facility_name': 'Hamilton Rec Center',
  'latitude': 37.78442364,
  'longitude': -122.43601635,
  'property_type': 'Neighborhood Park or Playground',
  'address': '1900 Geary Blvd',
  'district_zone': 'North',
  'source_data_as_of': '2025-12-18T09:04:01.000'},
 {'facility_id': 'RPD-132',
  'source_property_id': '132',
  'facility_name': 'Moscone Rec Center',
  'latitude': 37.80213066,
  'longitude': -122.4331224,
  'property_type': 'Neighborhood Park or Playground',
  'address': '1800 Chestnut St',
  'district_zone': 'North',
  'source_data_as_of': '2025-12-18T09:04:01.000'},
 {'facility_id': 'RPD-150',
  'source_property_id': '150',
  'facility_name': 'Joe DiMaggio Playground',
  'latitude': 37.80249695,
  'longitude': -122.41216884,
  'property_type': 'Neighborhood Park or Playground',
  'address': '651 Lombard Street',
  'district_zone': 'East',
  'source_data_as_of': '2025-12-18T09:04:01.000'},
 {'facility_id': 'RPD-164',
  'source_property_id': '164',
  'facility_name': 'Crocker Amazon Playground',
  'latitude': 37.7140419,
  'longitude': -122.42928813,
  'property_type': 'Regional Park',
  'address': '799 Moscow St',
  'district_zone': 'South',
  'source_data_as_of': '2026-05-01T03:31:01.000'},
 {'facility_id': 'RPD-172',
  'source_property_id': '172',
  'facility_name': 'Richmond Rec Center',
  'latitude': 37.78327503,
  'longitude': -122.47798997,
  'property_type': 'Neighborhood Park or Playground',
  'address': '251 18th Ave',
  'district_zone': 'West',
  'source_data_as_of': '2026-10-02T14:52:50.742'},
 {'facility_id': 'RPD-28',
  'source_property_id': '28',
  'facility_name': 'John McLaren Park',
  'latitude': 37.71809698,
  'longitude': -122.41908038,
  'property_type': 'Regional Park',
  'address': '100 John F Shelley Dr',
  'district_zone': 'South',
  'source_data_as_of': '2026-05-01T03:31:12.000'},
 {'facility_id': 'RPD-31',
  'source_property_id': '31',
  'facility_name': "St. Mary's Rec Center",
  'latitude': 37.73367487,
  'longitude': -122.42067123,
  'property_type': 'Neighborhood Park or Playground',
  'address': '95 Justin Dr',
  'district_zone': 'South',
  'source_data_as_of': '2025-12-18T09:05:20.000'},
 {'facility_id': 'RPD-52',
  'source_property_id': '52',
  'facility_name': 'Potrero Hill Rec Center',
  'latitude': 37.75614147,
  'longitude': -122.39693963,
  'property_type': 'Neighborhood Park or Playground',
  'address': '801 Arkansas St',
  'district_zone': 'East',
  'source_data_as_of': '2025-12-18T09:04:01.000'},
 {'facility_id': 'RPD-63',
  'source_property_id': '63',
  'facility_name': 'Mission Dolores Park',
  'latitude': 37.75975462,
  'longitude': -122.42712797,
  'property_type': 'Neighborhood Park or Playground',
  'address': '646 Dolores St',
  'district_zone': 'East',
  'source_data_as_of': '2025-12-18T09:05:20.000'},
 {'facility_id': 'RPD-66',
  'source_property_id': '66',
  'facility_name': 'Balboa Park',
  'latitude': 37.72495974,
  'longitude': -122.44462514,
  'property_type': 'Neighborhood Park or Playground',
  'address': '51 Havelock St',
  'district_zone': 'South',
  'source_data_as_of': '2025-12-18T09:05:04.000'},
 {'facility_id': 'RPD-756665',
  'source_property_id': '756665',
  'facility_name': 'Golden Gate Park - Section 1',
  'latitude': 37.77139097,
  'longitude': -122.45529391,
  'property_type': 'Regional Park',
  'address': '501 Stanyan St',
  'district_zone': 'West',
  'source_data_as_of': '2025-12-18T09:04:01.000'},
 {'facility_id': 'RPD-756666',
  'source_property_id': '756666',
  'facility_name': 'Golden Gate Park - Section 2',
  'latitude': 37.77090391,
  'longitude': -122.46603321,
  'property_type': 'Regional Park',
  'address': '501 Stanyan St',
  'district_zone': 'West',
  'source_data_as_of': '2025-12-18T09:04:01.000'},
 {'facility_id': 'RPD-756667',
  'source_property_id': '756667',
  'facility_name': 'Golden Gate Park - Section 3',
  'latitude': 37.76726835,
  'longitude': -122.47039125,
  'property_type': 'Regional Park',
  'address': '501 Stanyan St',
  'district_zone': 'West',
  'source_data_as_of': '2025-12-18T09:03:43.000'},
 {'facility_id': 'RPD-756668',
  'source_property_id': '756668',
  'facility_name': 'Golden Gate Park - Section 4',
  'latitude': 37.76889364,
  'longitude': -122.4790922,
  'property_type': 'Regional Park',
  'address': '501 Stanyan St',
  'district_zone': 'West',
  'source_data_as_of': '2025-12-18T09:04:01.000'},
 {'facility_id': 'RPD-756669',
  'source_property_id': '756669',
  'facility_name': 'Golden Gate Park - Section 5',
  'latitude': 37.76940891,
  'longitude': -122.49130313,
  'property_type': 'Regional Park',
  'address': '501 Stanyan St',
  'district_zone': 'West',
  'source_data_as_of': '2025-12-18T09:03:43.000'},
 {'facility_id': 'RPD-756670',
  'source_property_id': '756670',
  'facility_name': 'Golden Gate Park - Section 6',
  'latitude': 37.7677299,
  'longitude': -122.50423848,
  'property_type': 'Regional Park',
  'address': '501 Stanyan St',
  'district_zone': 'West',
  'source_data_as_of': '2025-12-18T09:03:17.000'},
 {'facility_id': 'RPD-93',
  'source_property_id': '93',
  'facility_name': 'Sunset Rec Center',
  'latitude': 37.75659386,
  'longitude': -122.48685659,
  'property_type': 'Neighborhood Park or Playground',
  'address': '2201 Lawton St',
  'district_zone': 'West',
  'source_data_as_of': '2025-12-18T09:04:42.000'},
 {'facility_id': 'RPD-957231',
  'source_property_id': '957231',
  'facility_name': 'Golden Gate Park - Section 7',
  'latitude': 37.76845534,
  'longitude': -122.46075895,
  'property_type': 'Regional Park',
  'address': '501 Stanyan St',
  'district_zone': 'West',
  'source_data_as_of': '2025-12-18T09:03:17.000'})


def facilities_frame() -> pd.DataFrame:
    """Return an independent copy of the curated, non-exhaustive inventory."""
    return pd.DataFrame(FACILITIES).assign(source_url=SOURCE_URL)


def attach_facilities(permits: pd.DataFrame) -> pd.DataFrame:
    """Attach one illustrative property to each permit, without changing SQLite.

    Sort source IDs within each invented zone, then use SHA-256 of permit ID
    modulo pool size. Allocation is stable across filters and row order. It is
    uniform within zone and does not establish category eligibility, available
    amenities, capacity, or a real reservation relationship.
    """
    facilities = facilities_frame()
    pools = {zone: sorted(group.facility_id) for zone, group in facilities.groupby('district_zone')}
    if not permits.district_zone.isin(pools).all():
        raise ValueError('No reference facility pool for an analytical zone')
    result = permits.copy()
    result['facility_id'] = [
        pools[zone][int(sha256(permit_id.encode('utf-8')).hexdigest(), 16) % len(pools[zone])]
        for permit_id, zone in zip(result.permit_id, result.district_zone)
    ]
    return result.merge(facilities.drop(columns='district_zone'), on='facility_id', how='left', validate='many_to_one')


def facility_demand(permits: pd.DataFrame) -> pd.DataFrame:
    """Aggregate assigned synthetic records, retaining zero-count reference sites."""
    counts = permits.groupby('facility_id').agg(
        permit_count=('permit_id', 'size'), overdue_pending=('pending_overdue', 'sum'),
        collected_fee_cents=('collected_fee_cents', 'sum'))
    return facilities_frame().merge(counts, on='facility_id', how='left').fillna(
        {'permit_count': 0, 'overdue_pending': 0, 'collected_fee_cents': 0})
