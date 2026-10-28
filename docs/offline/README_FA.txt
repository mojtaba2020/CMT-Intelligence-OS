CMT Offline v3.8 — HTTPS installable standalone PWA

1. Publish THIS DIRECTORY to HTTPS. On iPhone/iPad open the HTTPS link with Safari (not a ChatGPT webview), tap Share > Add to Home Screen, open the installed app.
2. Unlock with a 12+ character passphrase. A wrong passphrase is rejected if reports already exist. No password recovery.
3. Enter only synthetic test data during validation. Each report saves encrypted to IndexedDB. Do not depend on device storage as the sole copy.
4. Export encrypted JSON backup after EVERY shift. Verify saved file exists in Files/iCloud/other controlled storage and test restoring a synthetic record on a second test device.
5. Test airplane mode: after first successful online load, close the PWA, enable airplane mode, reopen and edit a synthetic record. Disable private browsing.
6. 2,000 local reports is a software guard, not a capacity guarantee. iOS may evict storage. Do not delete/reinstall app without exporting all data.
7. Twelve preliminary test templates are not certified ASTM/AASHTO methods; no automatic engineering approval.
8. No online backend, cloud sync, automatic technician-to-engineer transfer, or ElmTree connection is included. GitHub Pages only serves public JS/CSS/HTML; it does not see browser-stored report contents.
9. Static files are public. Never commit passwords, company records, backups, private keys, or API tokens to this folder.
