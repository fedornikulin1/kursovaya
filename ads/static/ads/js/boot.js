/* Never let an animation prevent access to the page, even if the main script fails. */
(() => {
  const root = document.documentElement;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const started = performance.now();
  root.classList.add("page-loading");
  const ready = () => {
    if (document.body?.classList.contains('reduce-motion')) {
      root.classList.remove('page-loading'); root.classList.add('page-ready'); return;
    }
    window.setTimeout(
      () => {
        root.classList.remove("page-loading");
        root.classList.add("page-ready");
      },
      Math.max(0, 180 - (performance.now() - started)),
    );
  };
  window.addEventListener("load", ready, { once: true });
  window.addEventListener("pageshow", ready);
  window.setTimeout(ready, 1400);
})();
