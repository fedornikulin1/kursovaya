/* Original progressive enhancement: photo deck, glyph reels and an SVG ribbon.
   Inspired by public previews, without React Bits Pro source or dependencies. */
(() => {
  const root = document.querySelector("[data-hero-showcase]");
  if (!root) return;

  const media = matchMedia("(prefers-reduced-motion: reduce)");
  const toggle = root.querySelector("[data-showcase-toggle]");
  const gallery = root.querySelector("[data-hero-gallery]");
  const deck = root.querySelector("[data-hero-deck]");
  const cards = [...root.querySelectorAll("[data-hero-card]")];
  const dots = [...root.querySelectorAll("[data-hero-dot]")];
  const count = root.querySelector("[data-hero-count]");
  const progress = root.querySelector("[data-hero-progress]");
  const ribbon = root.querySelector("[data-hero-ribbon]");
  const lead = root.querySelector("[data-glyph-lead]");
  const accent = root.querySelector("[data-glyph-lottery]");
  const phrases = ["у своих.", "для учёбы.", "для общаги."];
  const glyphs = "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЭЮЯ";
  const duration = 5500;
  const glyphAnimations = new Set();
  let index = 0;
  let phrase = 0;
  let paused = false;
  let hovering = false;
  let focused = false;
  let touching = false;
  let suspended = false;
  const initialBounds = root.getBoundingClientRect();
  let inView = initialBounds.top < innerHeight && initialBounds.bottom > 0;
  let glyphStarted = false;
  let ribbonReady = false;
  let ribbonStarted = false;
  let glyphTimer;
  let galleryTimer;
  let galleryStarted = 0;
  let remaining = duration;
  let progressAnimation;

  const reduced = () =>
    media.matches || document.body.classList.contains("reduce-motion");
  const running = () =>
    !paused && !reduced() && inView && !document.hidden && !suspended;

  function settleGlyphs() {
    glyphAnimations.forEach((animation) => animation.cancel());
    glyphAnimations.clear();
    lead.textContent = "Всё нужное —";
    accent.textContent = phrases[phrase];
  }

  function spinGlyphs(element, value) {
    element.replaceChildren();
    [...value].forEach((letter, i) => {
      const cell = document.createElement("span");
      cell.className = "glyph-cell";
      const measure = document.createElement("span");
      measure.className = "glyph-measure";
      measure.textContent = letter === " " ? "\u00a0" : letter;
      const strip = document.createElement("span");
      strip.className = "glyph-strip";
      const rows = letter === " " ? 0 : 5 + (i % 3);
      for (let row = 0; row <= rows; row++) {
        const symbol = document.createElement("span");
        symbol.className = "glyph-symbol";
        symbol.textContent =
          row === rows
            ? measure.textContent
            : glyphs[Math.floor(Math.random() * glyphs.length)];
        strip.append(symbol);
      }
      cell.append(measure, strip);
      element.append(cell);
      if (!rows) return;
      const animation = strip.animate(
        [
          { transform: "translateY(0)" },
          { transform: `translateY(-${(rows * 100) / (rows + 1)}%)` },
        ],
        {
          duration: 700 + (i % 3) * 90,
          delay: i * 38,
          easing: "cubic-bezier(.15,.8,.25,1)",
          fill: "both",
        },
      );
      glyphAnimations.add(animation);
      animation.finished.then(
        () => {
          glyphAnimations.delete(animation);
          if (!strip.isConnected) return;
          strip.replaceChildren(strip.lastElementChild);
          cell.classList.add("is-settled");
          animation.cancel();
        },
        () => glyphAnimations.delete(animation),
      );
    });
  }

  function syncGlyphs() {
    if (!running()) {
      clearTimeout(glyphTimer);
      glyphTimer = undefined;
      settleGlyphs();
      return;
    }
    if (!glyphStarted) {
      glyphStarted = true;
      spinGlyphs(lead, "Всё нужное —");
      spinGlyphs(accent, phrases[phrase]);
    }
    if (!glyphTimer) {
      glyphTimer = setTimeout(() => {
        glyphTimer = undefined;
        phrase = (phrase + 1) % phrases.length;
        spinGlyphs(accent, phrases[phrase]);
        syncGlyphs();
      }, 6500);
    }
  }

  function stopGalleryClock() {
    if (galleryTimer !== undefined) {
      clearTimeout(galleryTimer);
      galleryTimer = undefined;
      remaining = Math.max(0, remaining - (performance.now() - galleryStarted));
    }
    progressAnimation?.pause();
  }

  function resetGalleryClock() {
    clearTimeout(galleryTimer);
    galleryTimer = undefined;
    remaining = duration;
    progressAnimation?.cancel();
    progressAnimation = progress?.animate(
      [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }],
      { duration, fill: "both" },
    );
    progressAnimation?.pause();
  }

  function syncGallery() {
    if (!running() || hovering || focused || touching || cards.length < 2) {
      stopGalleryClock();
      return;
    }
    if (galleryTimer !== undefined) return;
    galleryStarted = performance.now();
    progressAnimation?.play();
    galleryTimer = setTimeout(() => {
      galleryTimer = undefined;
      select(index + 1);
    }, remaining);
  }

  function select(next) {
    if (!cards.length) return;
    index = (next + cards.length) % cards.length;
    cards.forEach((card, i) => {
      const offset = (i - index + cards.length) % cards.length;
      card.dataset.position =
        offset === 0
          ? "front"
          : offset === 1
            ? "next"
            : offset === cards.length - 1
              ? "previous"
              : "away";
      card.tabIndex = offset ? -1 : 0;
      card.inert = offset !== 0;
      if (offset) card.setAttribute("aria-hidden", "true");
      else card.removeAttribute("aria-hidden");
    });
    dots.forEach((dot, i) => {
      if (i === index) dot.setAttribute("aria-current", "true");
      else dot.removeAttribute("aria-current");
    });
    count.textContent = `${index + 1} / ${cards.length}`;
    resetGalleryClock();
    syncGallery();
  }

  function syncRibbon() {
    if (!ribbonReady) return;
    if (running()) {
      if (!ribbonStarted) {
        ribbonStarted = true;
        ribbon
          .querySelectorAll("animate")
          .forEach((node) => node.beginElement());
      }
      ribbon.unpauseAnimations();
    } else ribbon.pauseAnimations();
  }

  function sync() {
    const still = reduced();
    root.classList.toggle("showcase-still", still);
    toggle.disabled = still;
    toggle.setAttribute("aria-pressed", String(paused));
    toggle.setAttribute(
      "aria-label",
      still
        ? "Анимации баннера отключены настройками"
        : paused
          ? "Запустить анимации баннера"
          : "Остановить анимации баннера",
    );
    toggle.querySelector("[data-showcase-toggle-icon]").textContent =
      still || paused ? "▶" : "Ⅱ";
    toggle.querySelector("[data-showcase-toggle-label]").textContent = still
      ? "Без анимации"
      : paused
        ? "Запустить анимации"
        : "Пауза анимаций";
    syncGlyphs();
    syncGallery();
    syncRibbon();
  }

  toggle.hidden = false;
  toggle.addEventListener("click", () => {
    paused = !paused;
    sync();
  });
  root
    .querySelector("[data-hero-prev]")
    ?.addEventListener("click", () => select(index - 1));
  root
    .querySelector("[data-hero-next]")
    ?.addEventListener("click", () => select(index + 1));
  dots.forEach((dot, i) => dot.addEventListener("click", () => select(i)));
  gallery.addEventListener("pointerenter", (event) => {
    if (event.pointerType !== "mouse") return;
    hovering = true;
    syncGallery();
  });
  gallery.addEventListener("pointerleave", () => {
    hovering = false;
    syncGallery();
  });
  gallery.addEventListener("focusin", () => {
    focused = true;
    syncGallery();
  });
  gallery.addEventListener("focusout", (event) => {
    focused = gallery.contains(event.relatedTarget);
    syncGallery();
  });

  // Horizontal touch gestures switch cards; vertical gestures remain page scrolling.
  let touch;
  let suppressClick = false;
  deck.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse") return;
    touch = { id: event.pointerId, x: event.clientX, y: event.clientY };
    suppressClick = false;
    touching = true;
    syncGallery();
  });
  deck.addEventListener("pointerup", (event) => {
    if (!touch || touch.id !== event.pointerId) return;
    const dx = event.clientX - touch.x;
    const dy = event.clientY - touch.y;
    touch = undefined;
    touching = false;
    if (Math.abs(dx) >= 45 && Math.abs(dx) > Math.abs(dy) * 1.3) {
      suppressClick = true;
      select(index + (dx < 0 ? 1 : -1));
    }
    syncGallery();
  });
  deck.addEventListener("pointercancel", () => {
    touch = undefined;
    touching = false;
    syncGallery();
  });
  deck.addEventListener(
    "click",
    (event) => {
      if (suppressClick) {
        event.preventDefault();
        suppressClick = false;
      }
    },
    true,
  );

  media.addEventListener("change", sync);
  document.addEventListener("visibilitychange", sync);
  const observer = new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    sync();
  });
  observer.observe(root);
  window.addEventListener("pagehide", () => {
    suspended = true;
    sync();
  });
  window.addEventListener("pageshow", () => {
    suspended = false;
    // Restored pages may still have keyboard focus inside the gallery.
    focused = gallery.contains(document.activeElement);
    hovering =
      matchMedia("(hover: hover)").matches && gallery.matches(":hover");
    sync();
  });

  select(0);
  sync();
  // Measure a whole repeated phrase after the font loads, so the loop has no jump.
  document.fonts.ready.then(() => {
    const text = ribbon.querySelector("[data-ribbon-phrase]");
    const scroll = ribbon.querySelector("[data-ribbon-scroll]");
    const period = text.getComputedTextLength();
    scroll.setAttribute("to", String(-period));
    scroll.setAttribute("dur", `${period / 52}s`);
    ribbonReady = true;
    syncRibbon();
  });
})();
