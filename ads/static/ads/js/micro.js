/* Django-native adaptations of React Bits Micro interactions (David Haz, 2026).
 * Original sources and MIT + Commons Clause notice: docs/third-party/react-bits.md.
 * Real fields, POST forms and the existing upload collection stay authoritative.
 */
(() => {
  const motionQuery = matchMedia("(prefers-reduced-motion: reduce)");
  const reduced = () =>
    motionQuery.matches || document.body.classList.contains("reduce-motion");

  for (const root of document.querySelectorAll("[data-peek-rating]")) {
    const labels = [...root.querySelectorAll("[data-rating-value]")];
    const inputs = labels.map((label) => label.querySelector("input"));
    const tip = root.querySelector("[data-rating-tip]");
    const caption = root.querySelector("[data-rating-caption]");
    const descriptions = [
      "Не понравилось",
      "Есть замечания",
      "Нормально",
      "Хорошо",
      "Всё отлично!",
    ];
    let preview = null;
    const selected = () => inputs.findIndex((input) => input.checked);
    function paint() {
      const current = preview ?? selected();
      labels.forEach((label, index) => {
        label.dataset.lit = String(index <= current);
        label.style.setProperty(
          "--peek-lift",
          !reduced() && preview !== null && index <= preview
            ? index === preview
              ? "-10px"
              : "-5px"
            : "0px",
        );
        label.style.setProperty(
          "--peek-scale",
          !reduced() && preview === index ? "1.14" : "1",
        );
      });
      tip.hidden = preview === null;
      if (preview !== null) {
        tip.textContent = descriptions[preview];
        tip.style.left = `${labels[preview].offsetLeft + labels[preview].offsetWidth / 2}px`;
      }
    }
    labels.forEach((label, index) => {
      label.addEventListener("pointerenter", (event) => {
        if (event.pointerType === "mouse") {
          preview = index;
          paint();
        }
      });
      inputs[index].addEventListener("change", () => {
        preview = null;
        caption.textContent = `${index + 1} из 5 · ${descriptions[index]}`;
        paint();
        if (!reduced()) {
          const glyph = label.querySelector(".micro-rating-glyph");
          glyph.getAnimations().forEach((animation) => animation.cancel());
          glyph.animate(
            [
              { transform: "scale(1)" },
              { transform: "scale(1.3)", offset: 0.35 },
              { transform: "scale(1)" },
            ],
            { duration: 320, easing: "cubic-bezier(.23,1,.32,1)" },
          );
        }
      });
    });
    root.addEventListener("pointerleave", () => {
      preview = null;
      paint();
    });
    root.addEventListener("focusout", () => {
      preview = null;
      paint();
    });
    motionQuery.addEventListener("change", paint);
    if (selected() >= 0)
      caption.textContent = `${selected() + 1} из 5 · ${descriptions[selected()]}`;
    paint();
  }

  for (const select of document.querySelectorAll("[data-jelly-select]")) {
    const group = document.createElement("div");
    group.className = "micro-jelly";
    group.setAttribute("role", "radiogroup");
    const label = document.querySelector(`label[for="${select.id}"]`);
    if (label) {
      label.id ||= `${select.id}-label`;
      group.setAttribute("aria-labelledby", label.id);
      label.addEventListener("click", (event) => {
        event.preventDefault();
        buttons[select.selectedIndex]?.focus();
      });
    } else group.setAttribute("aria-label", select.name);
    const options = [...select.options];
    const buttons = options.map((option, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "radio");
      const dot = document.createElement("span");
      dot.className = "micro-jelly-dot";
      dot.setAttribute("aria-hidden", "true");
      button.append(dot, document.createTextNode(option.textContent));
      button.addEventListener("click", () => choose(index));
      group.append(button);
      return button;
    });
    function paint() {
      const current = select.selectedIndex;
      const active = buttons[current];
      buttons.forEach((button, index) => {
        const checked = index === current;
        button.setAttribute("aria-checked", String(checked));
        button.tabIndex = checked ? 0 : -1;
        button.disabled = select.disabled || options[index].disabled;
        const sameRow = active && active.offsetTop === button.offsetTop;
        button.style.setProperty(
          "--jelly-x",
          !reduced() && sameRow ? `${Math.sign(index - current) * 3}px` : "0px",
        );
        button.style.setProperty(
          "--jelly-scale",
          !reduced() && checked ? "1.035" : "1",
        );
        button.style.setProperty(
          "--jelly-delay",
          `${Math.min(Math.abs(index - current), 3) * 15}ms`,
        );
      });
    }
    function choose(index) {
      if (select.disabled || options[index].disabled) return;
      select.value = options[index].value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      paint();
    }
    group.addEventListener("keydown", (event) => {
      if (
        ![
          "ArrowLeft",
          "ArrowRight",
          "ArrowUp",
          "ArrowDown",
          "Home",
          "End",
        ].includes(event.key)
      )
        return;
      event.preventDefault();
      const enabled = buttons
        .map((b, i) => (b.disabled ? -1 : i))
        .filter((i) => i >= 0);
      if (!enabled.length) return;
      const current = enabled.indexOf(select.selectedIndex);
      const forward = ["ArrowRight", "ArrowDown"].includes(event.key);
      const next =
        event.key === "Home"
          ? enabled[0]
          : event.key === "End"
            ? enabled.at(-1)
            : enabled[
                (current + (forward ? 1 : -1) + enabled.length) % enabled.length
              ];
      choose(next);
      buttons[next].focus();
    });
    select.classList.add("micro-native-select");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");
    select.after(group);
    select.addEventListener("change", paint);
    select.addEventListener("micro:sync", paint);
    select.addEventListener("invalid", (event) => {
      event.preventDefault();
      buttons[0]?.focus();
    });
    new ResizeObserver(paint).observe(group);
    new MutationObserver(paint).observe(select, {
      attributes: true,
      attributeFilter: ["disabled"],
    });
    motionQuery.addEventListener("change", paint);
    paint();
  }

  for (const root of document.querySelectorAll("[data-folder-float]")) {
    const trigger = root.querySelector("[data-folder-toggle]");
    const notes = root.querySelector("[data-folder-notes]");
    // Open links follow the trigger in keyboard order, independent of visual stacking.
    root.append(notes);
    let pinned = false;
    const set = (open) => {
      root.classList.toggle("is-open", open);
      trigger.setAttribute("aria-expanded", String(open));
      notes.querySelectorAll("a").forEach((link) => {
        link.tabIndex = open ? 0 : -1;
      });
      notes.setAttribute("aria-hidden", String(!open));
    };
    trigger.addEventListener("click", () => {
      pinned = !pinned;
      set(pinned);
    });
    root.addEventListener("pointerenter", (event) => {
      if (event.pointerType === "mouse") set(true);
    });
    root.addEventListener("pointerleave", () => {
      if (!pinned && !root.contains(document.activeElement)) set(false);
    });
    root.addEventListener("focusin", () => set(true));
    root.addEventListener("focusout", (event) => {
      if (!pinned && !root.contains(event.relatedTarget)) set(false);
    });
    root.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        pinned = false;
        trigger.focus();
        set(false);
      }
    });
    root.classList.add("is-enhanced");
    set(false);
    if (root.hasAttribute("data-folder-photos")) {
      const editor = root.closest("[data-photo-editor]");
      const cards = [...notes.children];
      const count = editor.querySelector("[data-photo-count]");
      const refresh = () => {
        const photos = [
          ...editor.querySelectorAll(
            "[data-selected-previews] img,[data-saved-cover] img,[data-saved-photo] img",
          ),
        ].filter((img) => {
          const saved = img.closest("[data-saved-photo]");
          const cover = img.closest("[data-saved-cover]");
          return !(
            saved?.querySelector("input")?.checked ||
            (cover &&
              (cover.classList.contains("is-replaced") ||
                editor.querySelector('[name="image-clear"]')?.checked))
          );
        });
        cards.forEach((card, index) => {
          let copy = card.querySelector("img");
          if (photos[index]) {
            if (!copy) {
              copy = document.createElement("img");
              copy.alt = "";
              card.prepend(copy);
            }
            copy.src = photos[index].src;
            card.classList.add("has-photo");
          } else {
            copy?.remove();
            card.classList.remove("has-photo");
          }
        });
        root.querySelector("[data-folder-caption]").textContent =
          `${count.textContent.replace("/", "из")} фото`;
      };
      new MutationObserver(refresh).observe(count, {
        childList: true,
        characterData: true,
        subtree: true,
      });
      refresh();
    }
  }

  const hold = document.querySelector("[data-hold-button]");
  if (hold) {
    const form = hold.closest("form");
    const label = hold.querySelector("[data-hold-label]");
    const progress = hold.querySelector("[data-hold-progress]");
    const help = document.querySelector("[data-hold-help]");
    const duration = 1200;
    let start = null,
      frame = 0,
      pointer = null,
      key = null,
      armed = false;
    const initialHelp =
      "Удерживай 1,2 секунды и отпусти для удаления. С клавиатуры — удерживай пробел или Enter. Escape отменяет.";
    function paint(value) {
      hold.style.setProperty(
        "--hold-progress",
        reduced() ? Math.floor(value * 4) / 4 : value,
      );
      progress.setAttribute("aria-valuenow", String(Math.round(value * 100)));
      hold.classList.toggle("is-ready", value >= 1);
    }
    function reset() {
      cancelAnimationFrame(frame);
      start = null;
      pointer = null;
      key = null;
      hold.classList.remove("is-holding");
      label.textContent = "Удерживай для удаления";
      help.textContent = initialHelp;
      paint(0);
    }
    function tick(now) {
      if (start === null) return;
      const value = Math.min(1, (now - start) / duration);
      paint(value);
      if (value < 1) frame = requestAnimationFrame(tick);
      else {
        label.textContent = "Отпусти для удаления";
        help.textContent =
          "Готово. Отпусти кнопку для удаления или нажми Escape для отмены.";
      }
    }
    function begin() {
      if (start !== null || armed) return;
      start = performance.now();
      hold.classList.add("is-holding");
      label.textContent = "Продолжай удерживать…";
      help.textContent = "Раннее отпускание отменит удаление.";
      frame = requestAnimationFrame(tick);
    }
    function finish() {
      const ready = start !== null && performance.now() - start >= duration;
      reset();
      if (ready) {
        armed = true;
        label.textContent = "Удаляем…";
        form.requestSubmit(hold);
      } else help.textContent = initialHelp;
    }
    hold.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || start !== null) return;
      event.preventDefault();
      hold.focus();
      pointer = event.pointerId;
      hold.setPointerCapture(event.pointerId);
      begin();
    });
    hold.addEventListener("pointermove", (event) => {
      if (event.pointerId !== pointer) return;
      const rect = hold.getBoundingClientRect();
      if (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
      ) {
        reset();
        help.textContent = initialHelp;
      }
    });
    hold.addEventListener("pointerup", (event) => {
      if (event.pointerId === pointer) finish();
    });
    hold.addEventListener("pointercancel", reset);
    hold.addEventListener("lostpointercapture", () => {
      if (!armed) reset();
    });
    hold.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        reset();
        help.textContent = initialHelp;
        return;
      }
      if (![" ", "Enter"].includes(event.key)) return;
      event.preventDefault();
      if (!event.repeat && start === null) {
        key = event.key;
        begin();
      }
    });
    hold.addEventListener("keyup", (event) => {
      if (event.key === key) {
        event.preventDefault();
        finish();
      }
    });
    hold.addEventListener("click", (event) => {
      event.preventDefault();
      if (!armed && start === null) help.textContent = initialHelp;
    });
    hold.addEventListener("blur", () => {
      if (!armed) reset();
    });
    form.addEventListener("submit", (event) => {
      if (!armed && !event.submitter?.hasAttribute("data-hold-fallback")) {
        event.preventDefault();
        reset();
        hold.focus();
        help.textContent = initialHelp;
      }
    });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) reset();
    });
    window.addEventListener("blur", reset);
    window.addEventListener("pageshow", () => {
      armed = false;
      reset();
    });
    hold.classList.add("is-enhanced");
    document.querySelector("[data-hold-alternative]").hidden = false;
    help.textContent = initialHelp;
    reset();
  }
})();
