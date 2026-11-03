// Update only this app's worker. Cookies, accounts and saved records are untouched.
export async function applyAppUpdate({ serviceWorker, reload, timeoutMs = 6000, activationMessage = { type: 'SKIP_WAITING' } }) {
  const registration = await serviceWorker?.getRegistration();
  if (!registration) { reload(); return; }
  return new Promise((resolve, reject) => {
    let finished = false;
    const workers = new Set();
    function cleanup() {
      clearTimeout(timer);
      serviceWorker.removeEventListener('controllerchange', complete);
      registration.removeEventListener('updatefound', watchInstalling);
      for (const worker of workers) worker.removeEventListener('statechange', activateWaiting);
    }
    function complete() {
      if (finished) return;
      finished = true; cleanup(); reload(); resolve();
    }
    function fail(error) {
      if (finished) return;
      finished = true; cleanup(); reject(error);
    }
    function activateWaiting() {
      if (finished) return;
      registration.waiting?.postMessage(activationMessage);
    }
    function watchInstalling() {
      if (finished) return;
      const worker = registration.installing;
      if (worker && !workers.has(worker)) {
        workers.add(worker); worker.addEventListener('statechange', activateWaiting);
      }
      activateWaiting();
    }
    const timer = setTimeout(async () => {
      try {
        // A stale/external waiting-worker notification may never emit controllerchange.
        // Releasing this registration lets the next navigation load the current HTML.
        const removed = await registration.unregister();
        if (removed) complete();
        else fail(new Error('Close all Production Digital tabs and reopen the app to finish updating.'));
      } catch (error) { fail(error); }
    }, timeoutMs);
    serviceWorker.addEventListener('controllerchange', complete);
    registration.addEventListener('updatefound', watchInstalling);
    watchInstalling();
    if (!registration.waiting) Promise.resolve().then(() => registration.update()).then(watchInstalling).catch(fail);
  });
}
