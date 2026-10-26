# بروزرسانی v1.3 — گذرگاه ElmTree (Read-only / بدون اتصال مستقیم)

- ساخت ماژول mapping قابل تنظیم به فرمت‌های نمونه و مقایسه CSV با رکوردهای بازبینی‌شده.
- افزودن endpoint فقط خواندنی مهندس، کنترل یکپارچگی و عدم خروجی رکورد synthetic در مسیر مجاز.
- توسعه میزکار فارسی و فایل‌های نمایشی. همه قالب‌های مثال ساختگی‌اند و قالب بومی ElmTree نیستند.
- ۸۹ تست غیرمرورگری موفق (شامل ۱۸ تست پل). رابط پل جداگانه با مرورگر تست شد؛ مجموعه مرورگری قدیمی در این نوبت به‌طور کامل اجرا نشد.
- گام بعدی: بررسی مجاز فرمت خروجی/ورودی سازنده و اجرای پایلوت کنترل‌شده با داده ناشناس و دارای مجوز.

---

# Engineering release record — CMT Intelligence OS v1.0

## Completed and reproducible

1. Inherits local interactive catalog with 15 workflows and multi-point Proctor, sieve-stack, cylinder-set worksheets, example NDG/Proctor reconciliation, and optional opt-in photo extraction.
2. Role-separated local pilot with immutable revision rows, cross-linked SHA-256 audit, review lock, optimistic version checks and local-only access.
3. Added **server-side non-normative QA preflight** (`server/quality.py`) on drafts and selected records; submission is blocked on impossible arithmetic/data conditions and missing key measurements in implemented profiles. Warnings never become automated acceptance. The QA UI is in section 12 of the secure pilot tab.
4. Added **engineer-only vendor-neutral CSV** guarded by audit verification, explicitly marked uncertified and hardened for spreadsheet formula-prefix handling. No proprietary LIMS connection.
5. Added **SQLite consistent-backup CLI** (`server/backup.py`) verifying both DB and audit and refusing overwrite.
6. Added **offline label-and-time benchmark** (`validation/pilot_benchmark.py`) splitting synthetic and authorized data and reporting field accuracy, Wilson interval, abstentions, critical errors, paired time including correction and negative savings.
7. Passed all previous tests plus new API and Chromium QA workflow tests; generated traceable test results, source files and sample dataset.

## Major limitations

This is a local experimental release candidate with demonstration data. It has not been independently verified against licensed ASTM/AASHTO method editions, nor is it a certified engineering report, electronic signature, qualified acceptance determination, production security system or vendor-authorized ElmTree/GET connector. API OCR for real field documents is not benchmarked. A genuine rollout requires organizational consent, security architecture, signed-off method definitions, calibration and authorized representative datasets.

## Suggested pilot gate (negotiated with qualified reviewer, NOT ASTM pass criteria)

- Authorize a representative anonymized sample by a project or lab owner.
- Blind-label all critical fields with independent reviewer and adjudication.
- Log extraction failures, omissions, overconfident wrong values and correction minutes.
- Run manual and assisted workflows on comparable samples, including hard cases; analyze by test, form template and operator.
- Require no unresolved critical data-quality blockers to submit; preserve human-only sign-off and traceable corrections.
- Demonstrate full backup/restore drill and incident procedure on an approved deployment before storing employer/customer data.


## v1.1 implementation addendum
- All 15 minimum data-integrity QA profiles now fail closed on missing mandatory values.
- Local login attempt restriction persists after failed requests; not equivalent to SSO/MFA.
- Portable record-level report JSON includes revisions, findings, audit chain and checksum; not signed.
- Independent JSON checksum verifier plus clean-location restore drill tool.
- Synthetic input fixtures for each supported workflow and regression tests.
- Still requires licensed technical method validation, authorized real datasets and deployment review.
