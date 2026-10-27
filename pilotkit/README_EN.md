# CMT Pilot Evidence Pack v1.6

**Local-first demonstration, NOT a licensed ElmTree connector and NOT an automated AI extraction accuracy claim.**

## What it actually does

- Takes a JSON array of **independently transcribed** paired NDG or fresh-concrete records.
- Reuses the conservative v1.5 discrepancy screen (including metric/US customary unit conversion and identifier checks).
- Quarantines duplicate project/test pairs and reused source identifiers instead of silently merging.
- Produces an offline `summary.html`, a `review_queue.csv`, `report.json`, and a `manifest.json` with SHA-256 digests in a review-only ZIP.
- Checks manifest/file consistency via a separate `verify` command. This detects ordinary corruption or modification; it is **not** a digital signature or independent third-party attestation.
- Never calls ElmTree, the network, an LLM, or any production company system.

## Quick demonstration with synthetic cases

Run from the repository root:

```bash
python -m pilotkit.batch build --input pilotkit/examples/SYNTHETIC_BATCH_V16.json \
  --output CMT_Synthetic_Review_Bundle.zip --synthetic-demo
python -m pilotkit.batch verify --bundle CMT_Synthetic_Review_Bundle.zip
```

Open `summary.html` extracted from the ZIP in a browser. The ZIP is intended for *internal review*, not importing into any LIMS.

## Authorized pilot, not public GitHub

Only with an employer's written authorization, sanitized input and approved handling/security arrangements:

```bash
python -m pilotkit.batch build --input authorized_redacted_cases.json \
  --output internal_review_only.zip --authorized-data
```

`--authorized-data` records an operator declaration. The program **cannot verify the legal authorization**. Do not publish output, project IDs or photographs to a public repository. The ZIP contains some transcribed identifiers and values, even though it deliberately excludes original images. Treat it as potentially sensitive.

## Input schema

```json
{"cases": [
  {"test_type":"ndg", "synthetic":true,
   "screen_tolerances":{"wet_density":"0.2","moisture":"0.1"},
   "documents":[
     {"source_id":"FORM-1","source_type":"field_form","project_id":"DEMO-1","test_id":"NDG-1",
      "observations":[{"field":"wet_density","value":"128","unit":"pcf"},
                      {"field":"moisture","value":"12","unit":"%"}]},
     {"source_id":"GAUGE-1","source_type":"gauge_printout","project_id":"DEMO-1","test_id":"NDG-1",
      "observations":[{"field":"wet_density","value":"125","unit":"pcf"},
                      {"field":"moisture","value":"12","unit":"%"}]}
   ]}
]}
```

For concrete, use `test_type=fresh_concrete`, `source_type=concrete_ticket` and `slump`, `air`, `temperature`. This project does not determine compliance with a specific test method. All tolerances are **screening thresholds set by a qualified operator**, not ASTM/AASHTO acceptance rules.

## Safety boundaries

The program does not read photographic evidence, verify handwritten source authenticity, complete a chain of custody, provide engineering approval, prove business ROI, or write data to ElmTree. Human review is always required. Do not rely on demo values for field decisions.
