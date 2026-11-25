# Conformance assessments

This directory defines the format for **separately identified conformance assessments**: the frozen version-1 schema [`schema.json`](schema.json), the version-2 schema [`schema.v2.json`](schema.v2.json) and the index [`index.json`](index.json). It also holds the written rules below, the documentary fixtures AS1 to AS19 in [`fixtures/`](fixtures/), and their read-only checker [`check_assessments.py`](check_assessments.py).

The intake catalogue in [`../README.md`](../README.md) records specification `f18913c6ed062dc6d6c3d7a73dec7a33433b39e4`. Its 19 input records and pinned [`../INPUT-MANIFEST.v2.json`](../INPUT-MANIFEST.v2.json) are immutable. Its current presentation is generated from those inputs by the generator and template at the current source commit; `python3 -B generate.py --check` in `../` verifies equality of the nine generated outputs. The original generator, outputs and generation receipt remain available at Git commit `fc32a01fe7ec772940c143bce4f0973896a9decb`. All 787 implementation/evidence slots remain unassessed.

## Assessment index

[`index.json`](index.json) declares `schema_version` 2, is validated by [`schema.v2.json`](schema.v2.json), and contains `records: []`: **zero assessments have been ingested or claimed**. The historical intake counts referenced for provenance (`504` obligations, `271` historical follow-ups, `12` observation cases, and `90` pending destinations from `84` entries) are overlapping documentary categories, not additive completion denominators, and all `787` historical implementation/evidence slots remain unassessed.

## Three kinds of check

A JSON Schema checks the shape of one document. It cannot read a file at a commit, compare two submissions or keep a refused one. So three kinds of check are kept apart, and each rule in [Shape rules](#shape-rules), [Resolution rules](#resolution-rules) and [Import rules](#import-rules) (S1 to S3, R1 to R7 and I1 to I9) belongs to exactly one of them:

| Kind | What decides | Where it is written |
|---|---|---|
| Shape | The JSON Schema of the document's declared version | [`schema.json`](schema.json) (version 1, unchanged) and [`schema.v2.json`](schema.v2.json) (version 2), selected by the [shape rules](#shape-rules) |
| Resolution | The specification files at the subject's own `spec_commit` | The [resolution rules](#resolution-rules) |
| Identity and conflict | The set of submissions already kept | The [import rules](#import-rules) |

## Design rules

1. **Exact-subject and separate assessment identity.**
   A record binds an exact `subject` (component or composed release, exact `spec_commit`, requirement ID and revision, in schema version 2 the `requirement_occurrence` that it assesses, actor/duty and contract family, component/source/build/artifact identities, target, configuration digest, selected functions, structured `wire_direction_type_provider` object or `null` with required `wire`, `direction`, `message_type`, and nullable `allocation_provider` plus optional `memory_provider`, and optional assurance scope) separately from its `assessment` block (whose immutable identity is `producer_authority`, `assessment_id` and `assessment_revision` under [I1](#import-rules), alongside `assessor_review_identity`, ISO-8601 `YYYY-MM-DD` `observation_boundary_date`, `scope_label`, and `supersedes_or_revises`). A pin, an ID and a revision can name two different clauses, so a version-2 subject also names the occurrence of the requirement that it assesses. [`schema.json`](schema.json) is the frozen version-1 schema, whose subject has no occurrence; [`schema.v2.json`](schema.v2.json) is version 2, and a document's `schema_version` selects between them. The same duty on Linux serialized, QNX native, and an unoffered bare-metal combination carries separate scoped records.

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
- **S2. Two files, two identifiers.** Version-1 documents are validated against the frozen `schema.json`, which stays byte for byte unchanged. Version 2 is the separate file `schema.v2.json`, with its own `$id`, and defines no legacy form of a record. [`index.json`](index.json) declares `schema_version` 2 and is validated by `schema.v2.json`.
- **S3. The occurrence object.** In version 2 the subject has the required object `requirement_occurrence`, with exactly these members:
  - `source_path`: a string;
  - `ordinal`: a positive integer;
  - `anchor`: a string or `null`;
  - `service_version`: a string or `null`.

## Resolution rules

Resolution is decided by the specification files at the subject's own `spec_commit`, and any failure rejects the record. An *occurrence* of a requirement ID and revision is a block attribute line of an AsciiDoc file (a regular file whose path ends in `.adoc`) whose `oft-sid` attribute is exactly `<ID>~<revision>`; an attribute line in a verbatim, passthrough or comment block, or in a plain table cell, is not one.

- **R1. A version-1 record** has no occurrence. The resolver looks for occurrences of its ID and revision at its `spec_commit`, in the files that R3 admits. Exactly one: the record passes resolution with the occurrence that the resolver derived (if admitted under the import rules, kept by I3). More than one, or none: the submission is refused as *ambiguous* or *unresolvable* (kept by I4). Nothing is guessed.
- **R2. A version-2 record** carries the occurrence, and the resolver checks each of its members by R3 to R6.
- **R3. `source_path`** is the file's path relative to the repository root at `spec_commit`: forward slashes, no leading slash, and no empty, `.` or `..` segment, compared by exact characters. A path in another form is rejected, so that one occurrence has one accepted spelling. The file exists at that pin and is not under `conformance/`.
- **R4. `ordinal`** is the position of the occurrence among the occurrences of the exact `oft-sid` for that ID and revision in that file, in document order, counted from 1. That occurrence exists.
- **R5. `anchor`** equals the anchor that the resolver derives for that occurrence, and is `null` exactly when the resolver derives none. The derivation reads explicit anchors only, written `[[id]]`, `[[id,text]]` or `[#id]`, and the value is the bare `id`; an identifier that a renderer generates for a heading is not one.
  - *First form:* an explicit anchor on the line directly above the item's attribute line.
  - *Second form, otherwise:* an explicit anchor directly above the title of a section in which this item is the first block and the only item. A section here is its own body, from its title to the next title of any level, without its subsections.
  - *Otherwise none.* So an item in a table cell, one of several items under one anchored heading, an item that follows a NOTE or a paragraph in its section, and an item whose attribute line stands directly above a section title each have none, unless the first form applies. An anchor that only serves navigation is not a second accepted spelling.
- **R6. `service_version`** equals `<service>/v<N>` exactly when `source_path` begins with `up-l3/<service>/v<N>/`, and is `null` otherwise.
- **R7. Nothing is inferred across pins.** An item that moved has one path at an old pin and another at a new one, and each record uses the path at its own pin.

`anchor` and `service_version` corroborate the occurrence and add no identity beyond pin, path, ID, revision and ordinal: because each must equal exactly what the resolver derives, `null` included, two accepted subjects never differ in them alone.

## Import rules

Identity and conflict are decided by the set of submissions already kept.

- **I1. Identity.** Producer (`producer_authority`), `assessment_id` and `assessment_revision` stay the immutable identity of an assessment.
- **I2. The producer's bytes.** A stored submission is the producer's bytes. Normalization produces a comparison form only: it never rewrites a submission, and no historical identity changes.
- **I3. Version-1 documents and version-2 records stay apart.** A kept version-1 submission is a document of its own. The occurrence that the resolver derived for an admitted version-1 record (R1) is derived data, kept beside that submission. Neither is an element of a version-2 index's `records`.
- **I4. Refused version-1 submissions.** A version-1 submission refused as ambiguous or unresolvable (R1) is kept as a refused submission, with that reason.
- **I5. The comparison form** of a record is its JSON with object keys sorted, UTF-8, no insignificant whitespace, and arrays in the order submitted, with two exceptions: `subject.component_identities` and `subject.selected_functions` are sets, and in the comparison form their elements stand in the order of their own comparison forms, compared as byte strings. Every other array is a sequence, and its order is part of the content.
- **I6. Duplicate components.** A `component_identities` array with two equal elements is rejected.
- **I7. Equal subjects.** Two subjects are equal when their comparison forms are equal, the occurrence included. Subjects that differ only in occurrence are different subjects.
- **I8. No-ops and conflicts.** The same identity with an equal comparison form is an idempotent no-op. The same identity with a different one is refused, and both submissions are kept with their provenance.
- **I9. Corrections.** A correction is a new assessment revision that uses the existing `supersedes_or_revises` member; no new linking property is needed.

## Fixtures and checker

[`fixtures/`](fixtures/) holds the documentary cases AS1 to AS19, one directory each (`AS01` to `AS19`). Each case's `case.json` states its subject, its required outcome and the kind of check that decides it, and names the submissions, in the order received, with the outcome that the rules give each one. The submissions are documentary: none is a real assessment, and none qualifies a product.

[`check_assessments.py`](check_assessments.py) applies the shape, resolution and import rules to the fixtures against the specification files at each fixture's pin, and reports each outcome. For example, from this directory of a clone that holds the fixtures' pins:

```sh
python3 -I -B check_assessments.py --git-dir ../../.git
```

It is read-only: it opens no file for writing, uses no network, imports no real assessment and qualifies nothing. Its `--help` describes its options, the layout of the fixtures and of the derived data that it reports, and the subset of JSON Schema that it implements.

**Open comparison-form boundary (Q-3e-4):** I5 fixes key order, UTF-8 encoding and insignificant whitespace, and does not decide how equal JSON numbers written in different forms (such as `1` against `1.0`) compare. The checker does not normalize numbers; wherever an outcome would turn on how a number is written, it stops as undecided.

**Checker order of kinds (Q-3e-1):** The checker runs shape, then resolution, then identity, with short-circuit. That order is the checker's own, and whether a submission that fails more than one kind is kept (or which failure reason takes precedence) stays open for the format owner (Q-3e-1).

**Checker tool boundaries:** Syntactically valid JSON numbers are parsed as exact decimal values; where host integer-string conversion is required and exceeds the host limit (such as Python's `int_max_str_digits`), or where exact-integer expansion is required (such as `requirement_revision`, `assessment_revision`, schema integer bounds, or an in-range `ordinal`) and its exponent exceeds `1000` or its expanded digits exceed the host limit, the checker stops as `unsupported` (exit 2) rather than `unparseable`. Exact comparisons that do not require integer expansion (such as refusing an impossible `ordinal` like `1e1001` as `ordinal_absent`) complete without triggering the expansion bound. Local `#/$defs/<name>` schema references must be acyclic and within the checker's supported chain depth (`64`), schema nesting depth (`128`), and expanded traversal depth (`128`, counting nested subschemas and reference steps together). A schema with a cyclic `$ref`, deeper structure, invalid `pattern`, or non-object `$defs` is refused as `unsupported` (exit 2) before any case runs. Patterns exceeding the host regex compiler's repetition, numeric-conversion or recursion resources also stop as `unsupported` before any case runs. Schema patterns are restricted to the checker's greedy subset (with ASCII digits in brace quantifiers and no lazy or possessive `?`/`+` suffixes); syntax outside that subset—including lazy quantifiers valid in full ECMA-262—stops as `unsupported`. JSON container depth is limited to `384` (the root is depth `0`); a deeper parsed document or host decoder depth exhaustion stops as `unsupported`, rather than being classified as malformed. Schema validation permits at most `100000` schema/value evaluations per document, including repeated shared references and conditional branches; exhaustion stops as `unsupported`, rather than passing or failing the document. Composed validation that exhausts host stack resources also stops as `unsupported`. AsciiDoc recursive block/cell traversal is limited to depth `128` (the top level is `0`). AsciiDoc occurrence visibility is tracked within each parsed block or `a|` table cell scope (not by global physical line). List continuation attachment is tracked across continuation `+` markers, single-blank continuation transitions, and attached blocks within the same scope without claiming a general mixed-list parser: `[comment]` metadata survives active list continuation `+` transitions instead of prematurely releasing comment style, while an unresolved non-comment or overridden pending `oft-sid` head across a list continuation stops as `undecided` (`continuation_after_head`). The checker detects four unresolved list/metadata transitions within their actual parse scope and stops explicitly as file-level `undecided` whenever the queried requirement is relevant to the file: repeated `////` comment blocks during an active list continuation (`repeated_comment_block_in_list_continuation`), immediately adjacent pending block metadata or an attribute entry (attribute line, block title, or attribute entry) after an attached block followed by `+` (`adjacent_metadata_continuation_after_attached_block`; once armed, this conservative observer persists across intervening blank lines, `//` line comments, `////` comment blocks, directives, and further metadata or attribute-entry lines until reset by a non-`+` paragraph, list item, non-comment delimited block, heading, break, block macro, or scope exit, so a later standalone `+`—including a renderer-visible `+` paragraph—can still be conservatively refused), a single leading blank during an active list continuation (with or without already-pending metadata/style), followed by pending continuation metadata or an attribute entry, and a single following blank before a non-`+` line (`separated_blanks_around_continuation_metadata`), and a stale-list-context `+` transition after a terminating `//` line comment or `////` comment block with no active continuation (`list_continuation_after_terminating_comment`). Outside a list continuation, comment-styled standalone `+` is hidden as a comment paragraph, visible standalone `+` starts a real paragraph (contributing `+` and following lines including heading-shaped text kept in that paragraph), literal/verbatim-styled standalone `+` retains verbatim paragraph context (`in_verbatim_paragraph` on an immediately following `oft-sid`), and `+` inside an already-open non-list paragraph (including a comment or literal paragraph) ends that paragraph and starts a visible `+` paragraph. Top-level headings are classified as discrete/floating titles versus real section titles using the effective pending block style (`discrete`/`float` surviving blanks, line comments, and `////` blocks unless overridden by a later style such as `[""]`, `['']`, `[open]`, `[comment]`, or `[,role=...]`), and direct `oft-sid`-bearing discrete/floating titles stop conservatively as `undecided` (`discrete_heading_target`). Pending top-level metadata owned by an occurrence's own block does not act as a preceding-block barrier for second-form section-anchor derivation (while directives and real preceding visible blocks remain barriers), an unresolved `oft-sid` head before a `////` comment block that reaches a visible target stops as `undecided` rather than silently omitting the occurrence, a pending `oft-sid` head reaching a real later section title across `////`, blank lines or line comments retains section-target classification so the later-section `undecided` guard applies to an earlier sole item in the preceding anchored section, and unresolved blank- or line-comment-separated multiple pending `oft-sid` heads sharing a block's pending metadata (or an unresolved detached `oft-sid` head in an anchored section's own body, including a pending `oft-sid` head whose apparent target is an AsciiDoc attribute entry, flagged `target_is_attribute_entry`) stop conservatively as `undecided` during second-form anchor derivation rather than silently deriving `null`; direct queries targeting an `oft-sid` directly above an attribute entry also stop conservatively as `undecided` (`target_is_attribute_entry`), whereas an unheaded attribute entry outside the list-continuation transitions above is recorded as a non-visible `attribute_entry` line—creating no occurrence, triggering no `target_is_attribute_entry` flag and acting as no preceding-block barrier for second-form section-anchor derivation. The checker also stops conservatively as `undecided` for: `CELL_NOTES` physical-line column-style checks, non-overwritten `head_before_comment_block`, list-embedded `attribute_line_in_list_item`, `RT09` later-section attachment, description-list `[comment]` + `+` + adjacent `oft-sid`, and standalone comment-styled `+` + directly adjacent `oft-sid` without a blank line (`in_verbatim_paragraph`). These are tool support and resource limits, not new assessment schema constraints.

**Checker regression tests:** [`checker_tests/`](checker_tests/) holds labelled checker regression tests (separate from the AS1 to AS19 documentary fixtures in `fixtures/` described in [Fixtures and checker](#fixtures-and-checker)), carrying synthetic trees as JSON only (no AsciiDoc files and no `oft-sid` items). Run the normal cases with `python3 -I -B check_assessments.py --git-dir ../../.git --fixtures checker_tests/cases`; each directory under `checker_tests/stops/` is a single-case stop witness expected to exit 2 (`undecided` or `unsupported`). In `fixtures/`, AS4 (`configured_value: null`, decided by no check) and each step's `stored_bytes_unchanged` field are documentary statements, not behavioral checks.

This non-normative documentary structure establishes no product conformance, safety qualification, or runtime guarantee.
