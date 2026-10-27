> **v1.8 optional module:** Human-reviewed field capture schema and offline synthetic workbench are available in [`forms/README_V18_FA.md`](forms/README_V18_FA.md) and [`forms/Field_Capture_Review_v18.html`](forms/Field_Capture_Review_v18.html). No live ElmTree integration, production OCR, or use of employer originals.

# CMT Intelligence OS

**An experimental AI-assisted workflow for Construction Materials Testing (CMT).**

A vendor-neutral, local-first prototype for processing CMT field/laboratory measurements, spotting inconsistencies, preparing reviewer workflows, and creating **review-only** handoff packages.

> **Status:** Research/demo prototype (v1.5). **Not production-ready, not ASTM/AASHTO-certified, not a professional engineer's signed report.** It has **no live connection to ElmTree** or to any employer's systems. Included records and images are **synthetic examples**.

![CMT Intelligence OS interface](preview.png)

## Features

- Test-entry and preliminary quality checks across **15 CMT test/inspection workflows**, including soil density, Proctor, Atterberg limits, concrete, aggregate gradation, asphalt, and cover checks.
- Human review queue and local pilot API using Python, FastAPI, and SQLite.
- Prototype image-to-field extraction endpoint with opt-in external model configuration and mandatory manual verification (accuracy on real forms **not validated**).
- Offline, vendor-neutral **ElmTree Bridge concept**: field mapping, explicit units, reviewer gates, duplicate detection, synthetic CSV reconciliation, and checksummed handoff ZIPs. It **does not** use an official ElmTree import interface or API.
- Test/evidence and pilot-benchmark utilities; synthetic test success does not prove field accuracy, compliance, or time savings.

## See it without installing dependencies

Open [`index.html`](index.html) in a desktop browser. For the stand-alone review-only bridge, open [`bridge/ELMTREE_BRIDGE.html`](bridge/ELMTREE_BRIDGE.html).

Some functions (user accounts, server-side persistence, image extraction) require the local Python server.

## Run locally (Python 3.11+)

```bash
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m server.pilot create-user --username techdemo --role technician
python -m server.pilot create-user --username reviewdemo --role engineer
python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Create **distinct** users and strong passwords; no default login accounts are provided. Do not expose this local server to the public internet.

## Tests

```bash
python -m pytest -q -k 'not browser'
```

The published v1.4 baseline had **110 non-browser tests**. The v1.5 staging build passed **139 non-browser tests** locally; GitHub CI must be rerun after the v1.5 patch is committed. Browser tests require Playwright and its browser installation. The workflows still require independent technical validation against appropriately licensed standards.


## v1.5: NDG & concrete evidence reconciliation (read-only)

The new `server/reconcile_v15.py` compares a field form with a second independent
source (NDG gauge printout or concrete ticket), using **explicit units** and
**operator-supplied screening tolerances**. It catches mismatched test/project
identifiers, missing measurements, cross-document differences, and within-source
wet/dry-density calculation contradictions. This is **not AI accuracy validation**.

Open [`reconciliation_demo_v15.html`](reconciliation_demo_v15.html) offline to switch
between three **synthetic** scenarios. To run the Python reconciliation API locally:

```bash
python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
# Open http://127.0.0.1:8000/reconcile-demo
```

POST the JSON examples in `examples/v15/` to `/api/evidence/reconcile`.
The API never approves or persists a test or transmits any information to ElmTree.
Neither a clean comparison nor configured thresholds establish official acceptance.

## Synthetic data demo for the exchange bridge

```bash
python -m bridge.cli prepare \
  bridge/examples/SYNTHETIC_CMT_RECORDS.json \
  bridge/examples/SYNTHETIC_OPERATOR_PROFILE.json \
  --output bridge_review.csv --synthetic-demo
```

The generated CSV is a **review draft**, not an ElmTree-approved import file. Do not feed it into a production system without explicit authorization and documented format validation.

## Boundaries and privacy

- No live ElmTree integration or affiliation with ElmTree or its vendor. ElmTree is mentioned descriptively.
- Do not upload confidential employer/customer information, personal data, actual work orders, API keys, or internal software screenshots.
- Never use this prototype for official material acceptance decisions; qualified human review remains essential.
- Additional authentication, encryption, data isolation, backup/recovery, security review, regulatory/contractual controls, and approved deployment architecture are needed before production.
- Current data-validation criteria are not universal ASTM/AASHTO acceptance criteria.

See [`README_FA.md`](README_FA.md) for the detailed Persian guide, [`SECURITY_BOUNDARIES_FA.md`](SECURITY_BOUNDARIES_FA.md) for constraints, and [`bridge/README_FA.md`](bridge/README_FA.md) for the bridge usage.

## License

This public preview has **no open-source license** at present; public visibility does not by itself grant permission to reuse or redistribute the code. A license can be added later if the repository owner chooses to open-source it.


## v1.6 — Offline pilot review pack

The new `pilotkit` module screens multiple manually transcribed NDG/concrete evidence pairs and generates a manager-ready offline HTML review, engineer queue CSV and checkable review ZIP. It is **not live image OCR**, engineering acceptance, an ElmTree importer, or proof of commercial readiness.

```bash
python -m pilotkit.batch build --input pilotkit/examples/SYNTHETIC_BATCH_V16.json --output pilot_review.zip --synthetic-demo
python -m pilotkit.batch verify --bundle pilot_review.zip
```

See [`pilotkit/README_EN.md`](pilotkit/README_EN.md), [`pilotkit/MANAGER_PILOT_BRIEF_EN.md`](pilotkit/MANAGER_PILOT_BRIEF_EN.md), and [`pilotkit/ELMTREE_INTEGRATION_QUESTIONS_EN.md`](pilotkit/ELMTREE_INTEGRATION_QUESTIONS_EN.md).

## Field-form structure adapter (v1.7 experimental)

A new `forms/` module maps generic structures observed in four CMT field form types: daily report, concrete cylinder/strength sheet, multi-page in-place density record, and reinforcing observation. It performs **offline cross-form preflight on synthetic or authorized human-verified data**, detects missing/duplicate pages and test IDs, checks reported density arithmetic, and generates a review-only HTML report. No supplied employer photos or real record values are included, and this module does **not** perform OCR or ElmTree write access. See `forms/README_FA.md`.

## v1.9 — fully local photo OCR review laboratory

`forms/OCR_Review_v19.html` is served at `http://127.0.0.1:8000/ocr-lab` after the local server starts. Install the optional dependencies using `python -m pip install -r requirements-ocr.txt` and install the *Tesseract* executable with the English model on the same machine. This method never uploads the photo to a cloud OCR provider; it only returns OCR candidate lines and tentative source-backed field proposals. Tesseract scores are **not** calibrated confidence probabilities; dense handwriting/table extraction is not validated. Do not use real employer data without explicit permission and approved organizational security controls. All example images are neutral and synthetic.

The linked `forms/OCR_Review_v19_Offline_Demo.html` is an interactive, **pre-recorded synthetic OCR replay** for presenting on an iPhone without running Python. It does not perform live OCR. See `forms/README_V19_FA.md` and `RELEASE_NOTES_V19_FA.md` for details.

## New in v2.0 — Field Companion Mobile PWA

- `mobile/`: offline-first, installable (when hosted on HTTPS) mobile field review prototype.
- `docs/`: deployable copy for a **public demo** using GitHub Pages. Contains code only, no employer photos.
- `forms/table_rows_v20.py`: conservative local geometry-based detection of printed table row boundaries. No real handwriting accuracy claim.
- `validation/synthetic_table_benchmark_v20.py`: synthetic printed-line benchmark only.
- `integrations/elmtree_gateway_v20.py`: deliberately disabled vendor write gateway, awaiting official integration documentation and authorization.
- `RELEASE_NOTES_V20_FA.md`: full scope, limitations and testing details.

`python -m pytest -q -k 'not browser'` — 226 passed in latest run. `node mobile/test_core.js` and `node mobile/test_ocr_adapter.js` — 20 checks passed. Mobile UI smoke checks passed in headless Chromium. Full legacy browser-suite run did not complete within the environment's timeout; avoid treating it as passed.

**Safety boundary:** No live ElmTree connection, no calibrated handwriting accuracy, no official inspection/acceptance determination. Data persistence is local browser storage, not vetted for confidential company records. The mobile app has manual photo review; local machine OCR remains a separate optional workflow.
