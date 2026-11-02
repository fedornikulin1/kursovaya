(() => {
  const form = document.querySelector("#contact-form");
  document.querySelectorAll("[data-question]").forEach((button) =>
    button.addEventListener("click", () => {
      const field = form.querySelector("textarea");
      field.value = button.dataset.question;
      field.focus();
    }),
  );
  document
    .querySelector("[data-focus-contact]")
    ?.addEventListener("click", () =>
      form?.querySelector("textarea").focus({ preventScroll: true }),
    );
  const viewer = document.querySelector("[data-photo-viewer]");
  if (!viewer) return;
  const main = document.querySelector("#main-photo");
  const thumbs = [...document.querySelectorAll("[data-photo]")];
  const photos = [
    ...new Set(
      thumbs.length ? thumbs.map((button) => button.dataset.photo) : [main.src],
    ),
  ];
  const large = viewer.querySelector("[data-gallery-image]"),
    count = viewer.querySelector("[data-gallery-count]"),
    strip = viewer.querySelector("[data-gallery-thumbs]");
  const viewport = viewer.querySelector("[data-gallery-viewport]");
  const zoomButton = viewer.querySelector("[data-gallery-zoom]");
  let zoomed = false,
    drag = null;
  strip.hidden = photos.length < 2;
  viewer.classList.toggle("has-one-photo", photos.length === 1);
  function fitViewport() {
    if (!viewer.open || !large.complete || !large.naturalWidth) return;
    const single = photos.length === 1;
    const maximum = Math.min(
      innerHeight * (single ? 0.68 : 0.62),
      innerHeight * 0.92 - (single ? 80 : 150),
    );
    viewport.style.setProperty(
      "--gallery-fit-height",
      Math.min(
        maximum,
        (viewport.clientWidth * large.naturalHeight) / large.naturalWidth,
      ) + "px",
    );
  }
  large.addEventListener("load", fitViewport);
  window.addEventListener("resize", fitViewport);
  function setZoom(value) {
    zoomed = value;
    viewport.classList.toggle("is-zoomed", value);
    zoomButton.setAttribute("aria-pressed", String(value));
    zoomButton.setAttribute(
      "aria-label",
      value ? "Вписать фото в окно" : "Увеличить фото",
    );
    zoomButton.textContent = value ? "Вписать −" : "Увеличить +";
    requestAnimationFrame(() => {
      viewport.scrollLeft = value
        ? (viewport.scrollWidth - viewport.clientWidth) / 2
        : 0;
      viewport.scrollTop = value
        ? (viewport.scrollHeight - viewport.clientHeight) / 2
        : 0;
    });
  }
  zoomButton.addEventListener("click", () => setZoom(!zoomed));
  large.addEventListener("dblclick", () => setZoom(!zoomed));
  viewport.addEventListener("pointerdown", (event) => {
    if (!zoomed || event.pointerType !== "mouse" || event.button !== 0) return;
    drag = {
      x: event.clientX,
      y: event.clientY,
      left: viewport.scrollLeft,
      top: viewport.scrollTop,
    };
    viewport.setPointerCapture(event.pointerId);
    viewport.classList.add("is-panning");
    event.preventDefault();
  });
  viewport.addEventListener("pointermove", (event) => {
    if (!drag) return;
    viewport.scrollLeft = drag.left - (event.clientX - drag.x);
    viewport.scrollTop = drag.top - (event.clientY - drag.y);
  });
  const stopDrag = () => {
    drag = null;
    viewport.classList.remove("is-panning");
  };
  viewport.addEventListener("pointerup", stopDrag);
  viewport.addEventListener("pointercancel", stopDrag);
  let index = Math.max(
      0,
      photos.findIndex((url) => new URL(url, location.href).href === main.src),
    ),
    opener = null,
    touchX = null;
  function select(next) {
    setZoom(false);
    index = (next + photos.length) % photos.length;
    large.src = photos[index];
    main.src = photos[index];
    count.textContent = `${index + 1} / ${photos.length}`;
    strip.querySelectorAll("button").forEach((button, i) => {
      button.classList.toggle("is-selected", i === index);
      button.setAttribute("aria-pressed", String(i === index));
      if (viewer.open && i === index)
        button.scrollIntoView({ block: "nearest", inline: "center" });
    });
    thumbs.forEach((button) =>
      button.classList.toggle(
        "is-selected",
        button.dataset.photo === photos[index],
      ),
    );
    viewer.querySelector("[data-gallery-prev]").hidden = photos.length < 2;
    viewer.querySelector("[data-gallery-next]").hidden = photos.length < 2;
    requestAnimationFrame(fitViewport);
  }
  photos.forEach((url, i) => {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-label", `Фото ${i + 1}`);
    const img = document.createElement("img");
    img.src = url;
    img.alt = "";
    button.append(img);
    button.addEventListener("click", () => select(i));
    strip.append(button);
  });
  thumbs.forEach((button, i) =>
    button.addEventListener("click", () =>
      select(photos.indexOf(button.dataset.photo)),
    ),
  );
  const open = () => {
    opener = document.activeElement;
    select(index);
    viewer.showModal();
    fitViewport();
    document.documentElement.classList.add("gallery-open");
  };
  document.querySelector("[data-expand-photo]").addEventListener("click", open);
  main.addEventListener("click", open);
  main.style.cursor = "zoom-in";
  viewer
    .querySelector("[data-close-viewer]")
    .addEventListener("click", () => viewer.close());
  viewer.addEventListener("close", () => {
    stopDrag();
    setZoom(false);
    document.documentElement.classList.remove("gallery-open");
    opener?.focus({ preventScroll: true });
  });
  viewer.addEventListener("click", (event) => {
    if (event.target === viewer) viewer.close();
  });
  viewer
    .querySelector("[data-gallery-prev]")
    .addEventListener("click", () => select(index - 1));
  viewer
    .querySelector("[data-gallery-next]")
    .addEventListener("click", () => select(index + 1));
  viewer.addEventListener("keydown", (event) => {
    if (["+", "="].includes(event.key)) {
      event.preventDefault();
      setZoom(true);
      return;
    }
    if (["-", "0"].includes(event.key)) {
      event.preventDefault();
      setZoom(false);
      return;
    }
    if (zoomed && event.key.startsWith("Arrow")) {
      event.preventDefault();
      if (event.key === "ArrowLeft") viewport.scrollLeft -= 90;
      if (event.key === "ArrowRight") viewport.scrollLeft += 90;
      if (event.key === "ArrowUp") viewport.scrollTop -= 90;
      if (event.key === "ArrowDown") viewport.scrollTop += 90;
      return;
    }
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      select(index + (event.key === "ArrowRight" ? 1 : -1));
    }
  });
  large.addEventListener(
    "touchstart",
    (event) => {
      touchX =
        !zoomed && event.touches.length === 1
          ? event.changedTouches[0].clientX
          : null;
    },
    { passive: true },
  );
  large.addEventListener(
    "touchend",
    (event) => {
      if (zoomed || touchX === null) return;
      const distance = event.changedTouches[0].clientX - touchX;
      if (Math.abs(distance) > 45) select(index + (distance < 0 ? 1 : -1));
      touchX = null;
    },
    { passive: true },
  );
  select(index);
})();
