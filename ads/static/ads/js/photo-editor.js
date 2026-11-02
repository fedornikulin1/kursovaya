/* Files belong to the editor, not to a browser-specific writable FileList. */
(() => {
  const editor = document.querySelector("[data-photo-editor]");
  if (!editor) return;
  const form = editor.closest("form");
  const groups = [...editor.querySelectorAll("[data-upload-group]")].map(
    (element) => ({
      element,
      input: element.querySelector("[data-upload-input]"),
      files: [],
      urls: [],
    }),
  );
  const cover = groups.find(
    (group) => group.element.dataset.uploadGroup === "cover",
  );
  const coverClear = editor.querySelector('[name="image-clear"]');
  const savedCover = editor.querySelector("[data-saved-cover]");
  const status = editor.querySelector("[data-upload-status]");
  const summary = form.querySelector("[data-ad-errors]");
  const maximum = Number(editor.dataset.max);
  let saving = false;
  const count = () =>
    groups.reduce((sum, group) => sum + group.files.length, 0) +
    [...editor.querySelectorAll("[data-saved-photo] input")].filter(
      (input) => !input.checked,
    ).length +
    (savedCover && !cover.files.length && !coverClear.checked ? 1 : 0);
  const updateCount = () => {
    editor.querySelector("[data-photo-count]").textContent =
      `${count()} / ${maximum}`;
    if (coverClear) coverClear.disabled = saving || cover.files.length > 0;
    savedCover?.classList.toggle("is-replaced", cover.files.length > 0);
  };
  const selectionMessage = () => {
    status.dataset.tone = "success";
    status.textContent = `Выбрано ${count()} из ${maximum} фото${count() === maximum ? ". Для нового фото уберите одно из выбранных." : ". Можно добавить ещё."}`;
  };
  const fileError = (message) => {
    status.dataset.tone = "error";
    status.textContent = message;
  };
  function render(group) {
    group.urls.forEach((url) => URL.revokeObjectURL(url));
    group.urls = [];
    const container = group.element.querySelector("[data-selected-previews]");
    container.replaceChildren();
    group.files.forEach((file, index) => {
      const card = document.createElement("div");
      card.className = "selected-photo";
      const img = document.createElement("img");
      img.src = URL.createObjectURL(file);
      group.urls.push(img.src);
      img.alt = file.name;
      img.width = 112;
      img.height = 90;
      const caption = document.createElement("span");
      caption.textContent = file.name;
      caption.title = file.name;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Убрать ${file.name}`);
      remove.addEventListener("click", () => {
        if (saving) return;
        group.files.splice(index, 1);
        render(group);
        selectionMessage();
      });
      card.append(img, caption, remove);
      container.append(card);
    });
    updateCount();
  }
  function add(group, files) {
    if (saving) return;
    const batch = Array.from(files || []);
    if (!batch.length) return;
    if (group === cover && batch.length !== 1) {
      fileError("Для обложки выберите одно фото.");
      return;
    }
    for (const file of batch) {
      const supported =
        ["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
        (!file.type && /\.(jpe?g|png|webp)$/i.test(file.name));
      if (!supported || file.size > 5 * 1024 * 1024) {
        fileError(
          `«${file.name}»: нужны JPEG, PNG или WebP до 5 МБ. Предыдущий выбор сохранён.`,
        );
        return;
      }
    }
    const key = (file) => `${file.name}:${file.size}:${file.lastModified}`;
    const next =
      group === cover
        ? batch
        : [
            ...new Map(
              [...group.files, ...batch].map((file) => [key(file), file]),
            ).values(),
          ];
    const oldCover =
      savedCover && !coverClear.checked && !cover.files.length ? 1 : 0;
    const projected =
      count() -
      group.files.length +
      next.length -
      (group === cover ? oldCover : 0);
    if (projected > maximum) {
      fileError(
        `Можно выбрать до ${maximum} фото всего. Предыдущий выбор сохранён.`,
      );
      return;
    }
    const unchanged = group !== cover && next.length === group.files.length;
    if (group === cover && coverClear) coverClear.checked = false;
    group.files = next;
    render(group);
    selectionMessage();
    if (unchanged)
      status.textContent = `Эти фотографии уже есть в подборке. Выбрано ${count()} из ${maximum}.`;
  }
  for (const group of groups) {
    group.input.addEventListener("change", () => {
      const files = Array.from(group.input.files || []);
      // Clearing only the picker lets the user pick the same file again after removing it.
      group.input.value = "";
      add(group, files);
    });
    const zone = group.element.querySelector("[data-dropzone]");
    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (!saving) zone.classList.add("is-dragging");
    });
    zone.addEventListener("dragleave", () =>
      zone.classList.remove("is-dragging"),
    );
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("is-dragging");
      add(group, event.dataTransfer.files);
    });
  }
  editor.querySelectorAll("[type=checkbox]").forEach((input) =>
    input.addEventListener("change", () => {
      if (count() > maximum) {
        input.checked = !input.checked;
        fileError("Сначала уберите другое изображение: в подборке уже 8 фото.");
      } else selectionMessage();
      updateCount();
    }),
  );
  const price = form.querySelector('[name="price"]');
  const priceType = form.querySelector('[name="price_type"]');
  const priceField = price.closest("[data-price-field]");
  const kind = form.querySelector('[name="kind"]');
  let previousPriceType = priceType.value;
  let nonMonetary = false;
  function priceMode() {
    const nextNonMonetary = ["give", "exchange", "lend"].includes(kind.value);
    if (nextNonMonetary && !nonMonetary) {
      previousPriceType = priceType.value;
      priceType.value = "free";
    } else if (!nextNonMonetary && nonMonetary)
      priceType.value = previousPriceType;
    nonMonetary = nextNonMonetary;
    if (nonMonetary) priceType.value = "free";
    priceType.closest(".form-field").hidden = nonMonetary;
    const fixed = priceType.value === "fixed";
    priceField.hidden = !fixed;
    price.required = fixed;
    price.disabled = !fixed;
    price.setAttribute("aria-required", String(fixed));
    priceType.dispatchEvent(new Event("micro:sync"));
  }
  priceType.addEventListener("change", priceMode);
  kind.addEventListener("change", priceMode);
  priceMode();
  function clearErrors() {
    summary.hidden = true;
    summary.replaceChildren();
    form
      .querySelectorAll("[data-live-field-error]")
      .forEach((node) => node.remove());
    form
      .querySelectorAll('[aria-invalid="true"]')
      .forEach((node) => node.removeAttribute("aria-invalid"));
  }
  function showErrors(errors) {
    clearErrors();
    const title = document.createElement("strong");
    title.textContent =
      "Объявление пока не сохранено. Исправьте поля — фотографии остаются в подборке.";
    const list = document.createElement("ul");
    summary.append(title, list);
    for (const [name, items] of Object.entries(errors)) {
      const field = [...form.elements].find((element) => element.name === name);
      const label =
        {
          image: "Обложка",
          photos: "Дополнительные фотографии",
          delete_photos: "Сохранённые фотографии",
        }[name] ||
        (field?.id
          ? document
              .querySelector(`label[for="${field.id}"]`)
              ?.textContent.trim()
              .replace(/\s*\*$/, "")
          : "");
      const messages = items.map((item) =>
        typeof item === "string" ? item : item.message,
      );
      const line = document.createElement("li");
      line.textContent = (label ? label + ": " : "") + messages.join(" ");
      list.append(line);
      if (field) {
        field.setAttribute("aria-invalid", "true");
        const error = document.createElement("div");
        error.className = "field-errors";
        error.dataset.liveFieldError = "";
        error.textContent = messages.join(" ");
        (
          field.closest(".form-field") ||
          field.closest("[data-upload-group]") ||
          field
        ).after(error);
      }
    }
    summary.hidden = false;
    summary.focus({ preventScroll: true });
    summary.scrollIntoView({ behavior: "auto", block: "center" });
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saving) return;
    clearErrors();
    const body = new FormData(form);
    // Logging in in another tab can rotate Django's CSRF cookie.
    const csrfCookie = document.cookie
      .split("; ")
      .find((value) => value.startsWith("csrftoken="));
    if (csrfCookie)
      body.set(
        "csrfmiddlewaretoken",
        decodeURIComponent(csrfCookie.slice("csrftoken=".length)),
      );
    // Always append the actual collection; FileList assignment is not required.
    for (const group of groups) {
      body.delete(group.input.name);
      group.files.forEach((file) =>
        body.append(group.input.name, file, file.name),
      );
    }
    const controls = [
      ...form.querySelectorAll("input,textarea,select,button"),
    ].map((control) => [control, control.disabled]);
    const submit = form.querySelector('button[type="submit"]'),
      caption = submit.textContent;
    saving = true;
    form.setAttribute("aria-busy", "true");
    submit.textContent = "Сохраняем объявление…";
    controls.forEach(([control]) => (control.disabled = true));
    let navigating = false;
    try {
      const response = await fetch(form.action || location.href, {
        method: "POST",
        body,
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (response.redirected) throw new Error("session");
      if (!response.headers.get("content-type")?.includes("application/json"))
        throw new Error("response");
      const data = await response.json();
      if (!response.ok) {
        if (data.errors) {
          showErrors(data.errors);
          return;
        }
        throw new Error("response");
      }
      const redirect = new URL(data.redirect_url, location.origin);
      if (redirect.origin !== location.origin) throw new Error("origin");
      navigating = true;
      location.assign(redirect.href);
    } catch (error) {
      navigating = false;
      showErrors({
        __all__: [
          {
            message:
              error.message === "session"
                ? "Войдите в аккаунт в другой вкладке и повторите сохранение."
                : "Не удалось сохранить. Проверьте соединение и повторите попытку. Подборка фотографий сохранена на этой странице.",
          },
        ],
      });
    } finally {
      // Failed validation never replaces the form or its file collection.
      if (!navigating) {
        saving = false;
        controls.forEach(
          ([control, disabled]) => (control.disabled = disabled),
        );
        submit.textContent = caption;
        form.removeAttribute("aria-busy");
        updateCount();
      }
    }
  });
  window.addEventListener("pagehide", (event) => {
    if (!event.persisted)
      groups.forEach((group) =>
        group.urls.forEach((url) => URL.revokeObjectURL(url)),
      );
  });
  updateCount();
})();
