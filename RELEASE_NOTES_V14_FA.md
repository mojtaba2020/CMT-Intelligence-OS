# CMT Intelligence OS v1.4 — گزارش تحویل

**تاریخ:** ۲۵ اکتبر ۲۰۲۶  
**هدف این انتشار:** قابل بازرسی کردن تبادل آفلاین داده با خروجی CSV ناشناس/دارای مجوز؛ **نه اتصال مستقیم به ElmTree**.

## آنچه توسعه یافت

- `bridge/assurance.py`: گیت مستقل پیش از تبادل. همه فیلدهای اندازه‌گیریِ انتخاب‌شده باید واحد صریح در `profile.measurement_units` و `record.measurement_units` داشته باشند. این نرم‌افزار **تبدیل خودکار واحد یا تأیید حدود استاندارد انجام نمی‌دهد**.
- رکوردهایی که وضعیت بررسی مستقل، منبع مجاز/ساختگی، شناسه، کلید تطبیق، واحد اندازه‌گیری یا مقدار عددی معتبر ندارند قرنطینه می‌شوند.
- شناسه رکورد و کلید تطبیق تکراری قابل تطبیق حدسی نیستند؛ هر دو رکورد متعارض قرنطینه می‌شوند.
- خروجی با علامت `REVIEW_ONLY_NOT_VENDOR_IMPORT_APPROVED` تولید می‌شود.
- `python -m bridge.cli bundle`: بسته ZIP شامل CSV آماده بررسی، نقشه ستون‌ها، پیش‌پرواز و manifest با هش‌های SHA-256. بسته دارای محتوای داده است: آن را با مجوز نگهداری کنید.
- `python -m bridge.cli verify`: صحت داخلی فایل‌ها و تعداد رکوردها را بررسی می‌کند؛ **این بررسی امضای دیجیتال مستقل، تأیید هویت نویسنده یا اثبات اصالت داده نیست**. شخصی که همه محتویات و manifest را کنترل کند می‌تواند هش‌ها را دوباره محاسبه کند.
- `python -m bridge.cli audit-compare`: تطبیق با فایل CSV **ارائه‌شده توسط اپراتور**، گزارش اختلاف‌ها، کلیدهای مبهم، رکوردهای قرنطینه و سلول‌های شبه‌فرمولی.
- خروجی‌های CLI بدون `--force` روی فایل موجود بازنویسی نمی‌شوند.
- میزکار آفلاین مرورگر v1.4 نیز کنترل واحد و شناسه تکراری را قبل از تهیه CSV پیش‌نمایش اضافه کرده است؛ برای تهیه ZIP راستی‌آزمایی‌شده باید CLI اجرا شود.

## اجرای نمونه ساختگی

در پوشه ریشه پروژه، با Python 3.11+:

```bash
python -m bridge.cli preflight bridge/examples/SYNTHETIC_CMT_RECORDS.json bridge/examples/SYNTHETIC_OPERATOR_PROFILE.json --synthetic-demo --output v14_preflight.json
python -m bridge.cli bundle bridge/examples/SYNTHETIC_CMT_RECORDS.json bridge/examples/SYNTHETIC_OPERATOR_PROFILE.json --synthetic-demo --output v14_handoff.zip
python -m bridge.cli verify v14_handoff.zip --output v14_verification.json
python -m bridge.cli audit-compare bridge/examples/SYNTHETIC_CMT_RECORDS.json bridge/examples/SYNTHETIC_OPERATOR_PROFILE.json bridge/examples/SYNTHETIC_OPERATOR_EXPORT_WITH_CONFLICT.csv --synthetic-demo --output v14_comparison.json
```

مرورگر: فایل `bridge/ELMTREE_BRIDGE.html` را باز کنید، مثال ساختگی را انتخاب و سپس «ساخت CSV» و «مقایسه» را اجرا کنید.

## نتیجه آزمون‌ها

- **۱۱۰ تست غیرمرورگری موفق** در اجرای `python -m pytest -q -k 'not browser'` پیش از بسته‌بندی.
- **۳۹ تست اختصاصی پل قدیمی و جدید موفق**، که در عدد ۱۰۹ نیز لحاظ شده‌اند.
- رابط ElmTree Bridge v1.4 با Chromium در سناریوی ساختگی آزمایش شد: ۲ رکورد آماده، ۱ رکورد کنار گذاشته، ۱ اختلاف عددی، بدون خطای JavaScript.
- مجموعه کامل تست‌های مرورگری قدیمی در این نوبت پایان نیافت (اجرای ترکیبی از سقف زمانی ابزار عبور کرد). بنابراین ادعای «تمام تست‌های مرورگری» نداریم.

## موارد هنوز حل‌نشده

1. مستند رسمی یا محیط آزمایشی/API برای ورود اطلاعات به ElmTree. وجود خروجی QA، وجود یک روش ورود اطلاعات از نرم‌افزار ثالث را اثبات نمی‌کند.
2. داده‌های حقیقی ناشناس‌شده و دارای اجازه، برچسب‌های مرجع مستقل و نتایج نرخ خطا و صرفه‌جویی زمان AI.
3. بازبینی مسئول فنیِ استانداردهای ASTM/AASHTO با نسخه معتبر؛ کنترل‌های عددی فعلی جایگزین روش آزمون نیستند.
4. امنیت تولیدی، مجوزنامه، قرارداد داده و ارزیابی بیرونی توسط سازمان/مشتری.

**حفاظت اطلاعات:** هیچ داده‌ای از GET/ElmTree یا مشتریان واقعی در مثال‌ها نیست. فقط با اجازه کتبی از اطلاعات شرکت استفاده کنید. مسیر نوشتن به ElmTree فعال نیست.
