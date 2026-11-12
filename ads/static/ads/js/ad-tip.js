(() => {
  const tip = document.querySelector("[data-ad-tip]");
  if (!tip) return;

  const trigger = tip.querySelector("summary");
  const panel = tip.querySelector(".ad-tip-panel");
  const close = tip.querySelector("[data-ad-tip-close]");
  const controls = tip.querySelector("[data-ad-tip-controls]");
  const count = tip.querySelector("[data-ad-tip-count]");
  const next = tip.querySelector("[data-ad-tip-next]");
  const status = tip.querySelector("[data-ad-tip-status]");
  const track = tip.querySelector("[data-ad-tip-progress]");
  const slides = [...tip.querySelectorAll("[data-ad-tip-slide]")];
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const segments = slides.map(() => {
    const segment = document.createElement("span");
    segment.className = "ad-tip-segment";
    segment.append(document.createElement("span"));
    track.append(segment);
    return segment;
  });
  let activeIndex = 0;
  let progress;

  function stopProgress() {
    progress?.cancel();
    progress = undefined;
  }

  function render() {
    slides.forEach((slide, index) => {
      const current = index === activeIndex;
      slide.classList.toggle("is-current", current);
      slide.inert = !current;
      segments[index].classList.toggle("is-current", current);
      segments[index].classList.toggle("is-complete", index < activeIndex);
    });
    count.textContent = `${activeIndex + 1} / ${slides.length}`;
  }

  function advance(announce) {
    stopProgress();
    activeIndex = (activeIndex + 1) % slides.length;
    render();
    if (announce) {
      const slide = slides[activeIndex];
      status.textContent = `${slide.querySelector("h3").textContent}. ${slide.querySelector("p").textContent.trim()}`;
    }
    syncProgress();
  }

  function syncProgress() {
    if (!tip.open || reduced.matches || document.body.classList.contains("reduce-motion")) {
      stopProgress();
      return;
    }
    if (!progress) {
      const animation = segments[activeIndex].firstElementChild.animate(
        [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }],
        { duration: 7000, fill: "forwards" },
      );
      progress = animation;
      animation.onfinish = () => {
        if (progress === animation && tip.open) advance(false);
      };
    }
    const paused = document.hidden || panel.matches(":hover") || panel.contains(document.activeElement);
    if (paused) progress.pause();
    else progress.play();
  }

  function dismiss() {
    tip.open = false;
    trigger.focus({ preventScroll: true });
  }

  close.hidden = false;
  controls.hidden = false;
  render();
  close.addEventListener("click", dismiss);
  next.addEventListener("click", () => advance(true));
  tip.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && tip.open) dismiss();
  });
  tip.addEventListener("toggle", syncProgress);
  panel.addEventListener("pointerenter", syncProgress);
  panel.addEventListener("pointerleave", syncProgress);
  panel.addEventListener("focusin", syncProgress);
  panel.addEventListener("focusout", () => queueMicrotask(syncProgress));
  document.addEventListener("visibilitychange", syncProgress);
  reduced.addEventListener("change", syncProgress);

  if (tip.hasAttribute("data-ad-tip-auto")) tip.open = true;
})();
