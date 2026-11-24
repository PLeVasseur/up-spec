# Conformance assessments

This directory defines the successor documentary format for **separately identified conformance assessments**: the frozen version-1 schema [`schema.json`](schema.json), the version-2 schema [`schema.v2.json`](schema.v2.json) and the index [`index.json`](index.json).

It accompanies the immutable historical intake catalogue in [`../README.md`](../README.md) (`../INPUT-MANIFEST.v2.json` and `../intake.v2.json`) without modifying any historical intake record, generator output, or unassessed status. All 31 files in the historical intake catalogue remain reproducible via `python3 -B generate.py --check` in `../`.

## Current state

[`index.json`](index.json) declares `schema_version` 2, is validated by [`schema.v2.json`](schema.v2.json), and currently holds `records: []`: **zero assessments have been ingested or claimed**. The historical intake counts referenced for provenance (`504` obligations, `271` historical follow-ups, `12` observation cases, and `90` pending destinations from `84` entries) are overlapping documentary categories, not additive completion denominators, and all `787` historical implementation/evidence slots remain unassessed.

## Design rules

1. **Exact-subject and separate assessment identity.**
   A record binds an exact `subject` (component or composed release, exact `spec_commit`, requirement ID and revision, in schema version 2 the `requirement_occurrence` that it assesses, actor/duty and contract family, component/source/build/artifact identities, target, configuration digest, selected functions, structured `wire_direction_type_provider` object or `null` with required `wire`, `direction`, `message_type`, and nullable `allocation_provider` plus optional `memory_provider`, and optional assurance scope) separately from its `assessment` identity (`assessment_id`, `assessment_revision`, `producer_authority`, `assessor_review_identity`, ISO-8601 `YYYY-MM-DD` `observation_boundary_date`, `scope_label`, and `supersedes_or_revises`). A pin, an ID and a revision can name two different clauses, so a version-2 subject also names the occurrence of the requirement that it assesses. [`schema.json`](schema.json) is the frozen version-1 schema, whose subject has no occurrence; [`schema.v2.json`](schema.v2.json) is version 2, and a document's `schema_version` selects between them. The same duty on Linux serialized, QNX native, and an unoffered bare-metal combination carries separate scoped records.

2. **Independent status dimensions and coherence invariants.**
   A record separates `applicability` (`unknown`, `applicable`, or `not_applicable`), `implementation_fulfillment`, `evidence_sufficiency`, `offering_support_status`, `formal_claim_status`, `publication_transfer_status`, and non-empty `behavior_gaps` and `evidence_gaps` entries. Neither supplier offering nor a single metric collapses the others, and `unoffered` does not automatically mean `not_applicable`. To prevent contradictory records while keeping dimensions independent, the schema enforces:
   - `applicability: "not_applicable"` requires non-empty `applicability_reason` and `"not_applicable"` for both `implementation_fulfillment` and `evidence_sufficiency`, whereas `"applicable"` and `"unknown"` forbid `"not_applicable"` in either dimension.
   - `implementation_fulfillment: "fulfilled"` requires `behavior_gaps: []`.
   - `evidence_sufficiency: "sufficient"` requires at least one entry in `evidence` and `evidence_gaps: []`.

3. **Evidence access classes and verification limits.**
   Each immutable evidence entry declares its exact `source_helper_artifact_bindings` (preserving source/helper/artifact pins and freshness boundary) and one of four access classes:
   - `public_portable_artifact` (requires a non-null 64-character lowercase hex `digest_sha256`)
   - `public_pinned_link`
   - `controlled_access_artifact`
   - `historical_or_unavailable_locator`

   When an entry is `controlled_access_artifact` or `historical_or_unavailable_locator`, the schema enforces `public_composer_verified: false` and requires naming the `access_limited_assessor` and `assessment_basis_and_limits`; the public catalogue composer cannot claim independent verification where it lacks direct artifact access.

4. **Producer authority vs. central catalogue normalization.**
   The component or composition-package producer remains authoritative for its assessment record. The central catalogue imports, pins, and normalizes records for requirement-to-configuration and configuration-to-requirement navigation without issuing supplier or integrator claims.

5. **Historical provenance and independent `iceoryx2` observation dimensions.**
   Each record links to frozen intake IDs under `historical_intake_links` purely for provenance without rewriting historical status. When present, `iceoryx2_observation_dimensions` records six independent observation dimensions (`notification_call_errors`, `listener_notification`, `queue_receipt`, `consumption`, `corrupted_connection_skipping`, `arrival_deadline_observations`) with `limitation_discharges_requirement: false` enforced by the schema.

## Shape rules

Shape is decided by the JSON Schema of the document's declared version.

- **S1. Dispatch by version.** A submission is a document of the index shape from one producer. Its `schema_version` selects the schema: 1 selects the frozen [`schema.json`](schema.json), and 2 selects [`schema.v2.json`](schema.v2.json). Any other value is refused.
- **S2. Two files, two identifiers.** `schema.json` stays byte for byte as it is, so that older input is still validated against an unchanged schema. Version 2 is the separate file `schema.v2.json`, with its own `$id`. [`index.json`](index.json) declares `schema_version` 2 and is validated by `schema.v2.json`.
- **S3. The occurrence object.** In version 2 the subject has the required object `requirement_occurrence`, with exactly these members:
  - `source_path`: a string;
  - `ordinal`: a positive integer;
  - `anchor`: a string or `null`;
  - `service_version`: a string or `null`.

This non-normative documentary structure establishes no product conformance, safety qualification, or runtime guarantee.
