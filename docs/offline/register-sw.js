// Register only in an actual HTTPS origin. No background sync or upload.
if ('serviceWorker' in navigator && location.protocol === 'https:') {
  navigator.serviceWorker.register('./sw.js', {scope: './'}).then(reg => {
    // Refresh the service worker during an online visit; do not reload a dirty report.
    if (navigator.onLine) reg.update().catch(() => {});
  }).catch(err => { console.warn('Offline installation unavailable:', err); });
}
