# Conformance assessments

This directory defines the successor documentary format for **separately identified conformance assessments** ([`schema.json`](schema.json) and [`index.json`](index.json)).

It accompanies the immutable historical intake catalogue in [`../README.md`](../README.md) (`../INPUT-MANIFEST.v2.json` and `../intake.v2.json`) without modifying any historical intake record, generator output, or unassessed status. All 29 files in the historical intake catalogue remain reproducible via `python3 -B generate.py --check` in `../`.

## Current state

[`index.json`](index.json) currently holds `records: []`: **zero assessments have been ingested or claimed**. The historical intake counts referenced for provenance (`504` obligations, `271` historical follow-ups, `12` observation cases, and `90` pending destinations from `84` entries) are overlapping documentary categories, not additive completion denominators, and all `787` historical implementation/evidence slots remain unassessed.

## Design rules

1. **Exact-subject and separate assessment identity.**
   A record binds an exact `subject` (component or composed release, exact `spec_commit`, requirement ID and revision, actor/duty and contract family, component/source/build/artifact identities, target, configuration digest, selected functions, wire/direction/type/provider tuple, and optional assurance scope) separately from its `assessment` identity (`assessment_id`, `assessment_revision`, `producer_authority`, `assessor_review_identity`, `observation_boundary_date`, `scope_label`, and `supersedes_or_revises`). The same duty on Linux serialized, QNX native, and an unoffered bare-metal combination carries separate scoped records.

2. **Independent status dimensions.**
   A record separates `applicability` (`unknown`, `applicable`, or `not_applicable` with required reason), `implementation_fulfillment`, `evidence_sufficiency`, `offering_support_status`, `formal_claim_status`, `publication_transfer_status`, and simultaneous `behavior_gaps` and `evidence_gaps`. Neither supplier offering nor a single metric collapses the others, and `unoffered` does not automatically mean `not_applicable`.

3. **Evidence access classes and verification limits.**
   Each immutable evidence entry declares its exact `source_helper_artifact_bindings` (preserving source/helper/artifact pins and freshness boundary) and one of four access classes:
   - `public_portable_artifact`
   - `public_pinned_link`
   - `controlled_access_artifact`
   - `historical_or_unavailable_locator`

   When an entry is `controlled_access_artifact` or `historical_or_unavailable_locator`, the schema enforces `public_composer_verified: false` and requires naming the `access_limited_assessor` and `assessment_basis_and_limits`; the public catalogue composer cannot claim independent verification where it lacks direct artifact access.

4. **Producer authority vs. central catalogue normalization.**
   The component or composition-package producer remains authoritative for its assessment record. The central catalogue imports, pins, and normalizes records for requirement-to-configuration and configuration-to-requirement navigation without issuing supplier or integrator claims.

5. **Historical provenance and independent `iceoryx2` observation dimensions.**
   Each record links to frozen intake IDs under `historical_intake_links` purely for provenance without rewriting historical status. When present, `iceoryx2_observation_dimensions` records six independent observation dimensions (`notification_call_errors`, `listener_notification`, `queue_receipt`, `consumption`, `corrupted_connection_skipping`, `arrival_deadline_observations`) with `limitation_discharges_requirement: false` enforced by the schema.

This non-normative documentary structure establishes no product conformance, safety qualification, or runtime guarantee.
