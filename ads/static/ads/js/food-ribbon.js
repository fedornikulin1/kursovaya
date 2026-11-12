(() => {
  const ribbon = document.querySelector("[data-food-ribbon]");
  if (!ribbon) return;

  const handle = ribbon.querySelector("button");
  const track = ribbon.querySelector(".food-ribbon-track");
  const pause = document.querySelector("#food-ribbon-pause");
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const reduced = () => motion.matches || document.body.classList.contains("reduce-motion");
  const glideTime = 360;
  let period = 0, offset = 0, momentum = 0;
  let drag, skipClick = false, inView = true;
  let frameId, previousFrame = 0;

  function draw() {
    if (!period) return;
    offset = ((offset % period) + period) % period;
    track.style.transform = `translate3d(${-offset}px, 0, 0)`;
  }

  const visible = () => inView && !document.hidden;

  function schedule() {
    if (frameId === undefined && visible()) frameId = requestAnimationFrame(tick);
  }

  function tick(now) {
    frameId = undefined;
    if (!visible()) {
      previousFrame = 0;
      return;
    }
    const elapsed = previousFrame ? Math.min(34, now - previousFrame) : 0;
    previousFrame = now;
    const still = reduced();
    const autoplay = !still && !pause.checked && !drag;
    if (still) momentum = 0;
    if (!drag) {
      if (momentum) {
        const remaining = Math.exp(-elapsed / glideTime);
        offset += momentum * glideTime * (1 - remaining);
        momentum *= remaining;
        if (Math.abs(momentum) < .012) momentum = 0;
      } else if (autoplay) {
        offset += .032 * elapsed;
      }
    }
    draw();
    if (autoplay || momentum) schedule();
    else previousFrame = 0;
  }

  function measure() {
    const next = track.getBoundingClientRect().width / 2;
    if (period && next) offset *= next / period;
    period = next;
    draw();
  }

  handle.addEventListener("pointerdown", (event) => {
    if (!event.isPrimary || event.button !== 0) return;
    skipClick = false;
    momentum = 0;
    drag = { id: event.pointerId, x: event.clientX, time: event.timeStamp, speed: 0, moved: false };
    handle.setPointerCapture(event.pointerId);
    handle.classList.add("is-grabbing");
  });

  handle.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const distance = event.clientX - drag.x;
    if (!drag.moved && Math.abs(distance) < 4) return;
    const delta = distance * 1.12;
    const elapsed = Math.max(4, event.timeStamp - drag.time);
    const blend = 1 - Math.exp(-elapsed / 28);
    const velocity = drag.speed + (delta / elapsed - drag.speed) * blend;
    drag.speed = Math.max(-2.8, Math.min(2.8, velocity));
    drag.x = event.clientX;
    drag.time = event.timeStamp;
    drag.moved = true;
    offset -= delta;
    schedule();
  });

  function release(event) {
    if (!drag || event.pointerId !== drag.id) return;
    skipClick = drag.moved;
    if (!reduced() && drag.moved && event.type === "pointerup") {
      momentum = -drag.speed * Math.exp(-Math.max(0, event.timeStamp - drag.time) / 115);
    }
    drag = undefined;
    handle.classList.remove("is-grabbing");
    schedule();
  }

  for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
    handle.addEventListener(name, release);
  }

  function shift(distance) {
    momentum = 0;
    offset += distance;
    schedule();
  }

  handle.addEventListener("click", (event) => {
    if (!(event.detail && skipClick)) shift(65);
  });

  handle.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    shift(event.key === "ArrowLeft" ? 65 : -65);
  });

  pause.addEventListener("change", schedule);
  motion.addEventListener("change", schedule);
  document.addEventListener("visibilitychange", schedule);
  new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    schedule();
  }).observe(ribbon);
  new ResizeObserver(measure).observe(track);
  ribbon.classList.add("is-interactive");
  handle.hidden = false;
  measure();
  schedule();
})();
