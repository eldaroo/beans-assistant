// Bitácora AI — PWA install wiring.
// Registers the service worker on every page, and (where a #install-app button
// exists, e.g. the login page) drives the "Instalar en el celular" flow:
//   - Android/Chromium: captures beforeinstallprompt and fires the native installer.
//   - iOS Safari: no programmatic install exists, so it reveals manual instructions.
//   - Already installed / unsupported: the button stays hidden (no dead button).
(function () {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () {});
    });
  }

  function init() {
    var btn = document.getElementById("install-app");
    if (!btn) return;

    var iosHint = document.getElementById("ios-install-hint");
    var standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true;
    if (standalone) return; // already installed → nothing to offer

    var isIOS =
      /iphone|ipad|ipod/i.test(window.navigator.userAgent) && !window.MSStream;
    var deferred = null;

    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      deferred = e;
      btn.classList.remove("hidden");
    });

    window.addEventListener("appinstalled", function () {
      btn.classList.add("hidden");
      if (iosHint) iosHint.classList.add("hidden");
    });

    if (isIOS) {
      // iOS: show immediately; tap toggles the Share → "Agregar a inicio" hint.
      btn.classList.remove("hidden");
      btn.addEventListener("click", function () {
        if (iosHint) iosHint.classList.toggle("hidden");
      });
      return;
    }

    btn.addEventListener("click", function () {
      if (!deferred) return;
      deferred.prompt();
      deferred.userChoice.finally(function () {
        deferred = null;
        btn.classList.add("hidden");
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
