# Data sources and modeling provenance

The transactional CSV and SQLite tables are wholly synthetic. No applicant data,
internal queues, response logs, or portal uptime records are included.

## Public property inventory

- Dataset: [DataSF Recreation and Parks Properties](https://data.sf.gov/d/gtr9-ntp6)
- API: https://data.sf.gov/resource/gtr9-ntp6.json
- Retrieved: October 23, 2026
- Public inventory size at retrieval: 255 rows
- Curated reference subset: 19 rows
- Catalog: https://catalog.data.gov/dataset/recreation-and-parks-properties
- License listed in the catalog: Public Domain Dedication and License (PDDL 1.0),
  https://opendatacommons.org/licenses/pddl/1-0/
- Preserved evidence: `data/facility_source_excerpt.json`, including full-download
  SHA-256 and original property fields. `data/facility_reference.csv` is the curated export.

Names, coordinates, property IDs, addresses, and source record dates come from
that inventory. Coordinates identify property reference points, not entrances.
Golden Gate Park is retained as seven inventory sections. This is not a complete
catalog of reservable facilities, and permit category eligibility is not verified.

## Synthetic modeling

Category mix, fees, approval probability, seasonal intake, review duration,
calendar-day targets, and four analytical zones are assumptions. Facility
assignments use `zone-sha256-v1`, a stable hash of permit ID selecting a property
within the invented zone. These assignments have no observed booking relationship.
The code is MIT licensed; the public source data remains subject to its own terms.

## Unverified claims excluded

This project has not established whether particular transaction fields can be
released under public records law. Do not label all transactional queues legally
restricted without a specific authoritative source. The decision to use synthetic
records is a privacy-preserving scope choice, not a legal finding. The proposed
customer-based SLA framework is a design proposal, not verified department policy.
