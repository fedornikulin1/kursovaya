(() => {
  const media = matchMedia("(prefers-reduced-motion: reduce)");
  const clamp = (value, limit) => Math.max(-limit, Math.min(limit, value));
  const reduced = () => media.matches || document.body.classList.contains("reduce-motion");

  function attachMagnets(container, enabled) {
    const magnets = [...container.querySelectorAll("[data-showcase-magnet]")];
    function reset(wrap) {
      wrap.classList.remove("is-pulled");
      wrap.style.removeProperty("--magnet-x");
      wrap.style.removeProperty("--magnet-y");
    }
    for (const wrap of magnets) {
      wrap.addEventListener("pointermove", (event) => {
        if (!enabled() || event.pointerType !== "mouse") return;
        const rect = wrap.getBoundingClientRect();
        const x = clamp((event.clientX - rect.left - rect.width / 2) * 0.2, 7);
        const y = clamp((event.clientY - rect.top - rect.height / 2) * 0.27, 5);
        wrap.style.setProperty("--magnet-x", `${x}px`);
        wrap.style.setProperty("--magnet-y", `${y}px`);
        wrap.classList.add("is-pulled");
      });
      wrap.addEventListener("pointerleave", () => reset(wrap));
    }
    return () => magnets.forEach(reset);
  }

  const food = document.querySelector(".food-intro");
  if (food) {
    const reset = attachMagnets(food, () => !reduced() && !document.hidden);
    media.addEventListener("change", reset);
    document.addEventListener("visibilitychange", reset);
  }

  const root = document.querySelector("[data-hero-showcase]");
  if (!root) return;

  const toggle = root.querySelector("[data-showcase-toggle]");
  const accent = root.querySelector("[data-hero-type]");
  const jelly = root.querySelector("[data-showcase-jelly]");
  const wordmark = jelly.querySelector(".showcase-wordmark");
  const phrases = ["у своих.", "для учёбы.", "для общаги."];
  let phrase = 0;
  let letters = phrases[0].length;
  let deleting = true;
  let paused = false;
  let inView = false;
  let suspended = false;
  let typeTimer;
  let drag;
  let dragged = false;
  let jiggle;

  const running = () => !paused && !reduced() && inView && !document.hidden && !suspended;
  const resetMagnets = attachMagnets(root, running);

  function syncTyping() {
    clearTimeout(typeTimer);
    if (!running()) {
      accent.textContent = phrases[phrase];
      letters = phrases[phrase].length;
      deleting = true;
      return;
    }
    const step = () => {
      if (!running()) return;
      if (deleting) {
        if (--letters === 0) {
          deleting = false;
          phrase = (phrase + 1) % phrases.length;
        }
      } else if (++letters === phrases[phrase].length) {
        deleting = true;
      }
      accent.textContent = phrases[phrase].slice(0, letters);
      typeTimer = setTimeout(
        step, letters === phrases[phrase].length ? 2200 : letters === 0 ? 280 : deleting ? 65 : 105,
      );
    };
    typeTimer = setTimeout(step, 1800);
  }

  function releaseJelly() {
    drag = undefined;
    jelly.classList.remove("is-pulled");
    jelly.style.removeProperty("--jelly-pull");
  }

  function sync() {
    const still = reduced();
    root.classList.toggle("showcase-still", still);
    root.classList.toggle("showcase-paused", !running());
    toggle.disabled = still;
    jelly.disabled = still;
    toggle.setAttribute("aria-pressed", String(paused || still));
    toggle.setAttribute("aria-label", still ? "Анимации отключены настройками"
      : paused ? "Запустить анимации баннера" : "Остановить анимации баннера");
    toggle.querySelector("[data-showcase-toggle-icon]").textContent = paused || still ? "▶" : "Ⅱ";
    toggle.querySelector("[data-showcase-toggle-label]").textContent = still
      ? "Без анимации" : paused ? "Запустить анимации" : "Пауза анимаций";
    if (!running()) {
      resetMagnets();
      releaseJelly();
      jiggle?.cancel();
    }
    syncTyping();
  }

  toggle.hidden = false;
  toggle.addEventListener("click", () => {
    paused = !paused;
    sync();
  });

  jelly.addEventListener("pointerdown", (event) => {
    if (!running() || !event.isPrimary || event.button !== 0) return;
    jiggle?.cancel();
    dragged = false;
    const rect = jelly.getBoundingClientRect();
    const origin = 50 + clamp((event.clientX - rect.left) / rect.width * 100 - 50, 35);
    jelly.style.setProperty("--jelly-origin", `${origin}% 50%`);
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
    jelly.setPointerCapture(event.pointerId);
  });
  jelly.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!dragged && Math.hypot(dx, dy) < 4) return;
    dragged = true;
    const x = clamp(dx * 0.25, 11);
    const y = clamp(dy * 0.28, 8);
    const squash = Math.min(0.075, Math.hypot(x, y) / 155);
    jelly.style.setProperty("--jelly-pull",
      `translate(${x}px, ${y}px) skewX(${x * 0.4}deg) scale(${1 + squash}, ${1 - squash * 0.8})`,
    );
    jelly.classList.add("is-pulled");
  });
  jelly.addEventListener("lostpointercapture", releaseJelly);
  jelly.addEventListener("click", (event) => {
    if (!running() || (dragged && event.detail > 0)) return;
    jiggle?.cancel();
    jelly.style.removeProperty("--jelly-origin");
    jiggle = wordmark.animate([
      { transform: "scale(1)" },
      { transform: "scale(.95, 1.07)", offset: 0.23 },
      { transform: "scale(1.035, .97)", offset: 0.53 },
      { transform: "scale(1)" },
    ], { duration: 360, easing: "ease-out" });
  });

  media.addEventListener("change", sync);
  document.addEventListener("visibilitychange", sync);
  new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    sync();
  }).observe(root);
  window.addEventListener("pagehide", () => { suspended = true; sync(); });
  window.addEventListener("pageshow", () => { suspended = false; sync(); });
  sync();
})();
