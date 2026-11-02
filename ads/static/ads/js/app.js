/* Progressive enhancement: forms work without JavaScript. */
document.documentElement.classList.add("js-enabled");
const categoryGrid = document.getElementById("catalog-categories");
const categoryToggle = document.querySelector("[data-category-toggle]");
if (categoryGrid && categoryToggle) {
  const remaining = Math.max(0, categoryGrid.children.length - 6);
  const mobile = window.matchMedia("(max-width:700px)");
  let expanded = false;
  const updateCategories = () => {
    categoryGrid.classList.toggle("is-collapsed", mobile.matches && !expanded);
    categoryToggle.setAttribute("aria-expanded", String(expanded));
    categoryToggle.textContent = expanded
      ? "Свернуть категории ↑"
      : "Ещё категории · +" + remaining + " ↓";
  };
  categoryToggle.addEventListener("click", () => {
    expanded = !expanded;
    updateCategories();
  });
  mobile.addEventListener("change", updateCategories);
  updateCategories();
}
// Reveal content as it enters the viewport; no-JS and reduced-motion stay fully visible.
if (
  "IntersectionObserver" in window &&
  !matchMedia("(prefers-reduced-motion: reduce)").matches
) {
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.04 },
  );
  document
    .querySelectorAll(".listing-card, .filter-panel, .bottom-banner")
    .forEach((element, index) => {
      element.classList.add("reveal-ready");
      element.style.transitionDelay = Math.min((index % 3) * 45, 90) + "ms";
      observer.observe(element);
    });
}
for (const button of document.querySelectorAll("[data-price-preset]")) {
  button.addEventListener("click", () => {
    const form = button.form;
    form.querySelector("[name=price_min]").value = "";
    form.querySelector("[name=price_max]").value =
      button.dataset.pricePreset === "free" ? "" : button.dataset.pricePreset;
    form.querySelector("[name=price_type]").checked =
      button.dataset.pricePreset === "free";
    form.querySelector("[name=price_max]").focus();
  });
}
for (const image of document.querySelectorAll(".listing-visual img")) {
  const fallback = () => {
    const link = image.parentElement;
    if (link.classList.contains("image-failed")) return;
    link.classList.add("image-failed");
    const text = document.createElement("span");
    text.textContent = "Фотография недоступна";
    link.append(text);
  };
  image.addEventListener("error", fallback, { once: true });
  if (image.complete && image.naturalWidth === 0) fallback();
}
const csrf = () =>
  document.querySelector("input[name=csrfmiddlewaretoken]")?.value;
const announce = (text) => {
  let region = document.getElementById("action-status");
  if (!region) {
    region = document.createElement("p");
    region.id = "action-status";
    region.className = "sr-only";
    region.setAttribute("role", "status");
    document.body.append(region);
  }
  region.textContent = text;
};
for (const form of document.querySelectorAll("[data-favorite]")) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
        },
      });
      if (!response.ok || response.redirected) throw new Error("request");
      const data = await response.json();
      button.classList.toggle("is-active", data.is_favorite);
      button.setAttribute("aria-pressed", String(data.is_favorite));
      const label = form.querySelector("[data-favorite-label]");
      if (label)
        label.textContent = data.is_favorite ? "В избранном" : "В избранное";
      announce(
        data.is_favorite ? "Добавлено в избранное" : "Удалено из избранного",
      );
      if (window.location.pathname === "/favorites/" && !data.is_favorite) {
        form.closest(".listing-card")?.remove();
        if (!document.querySelector(".listing-card")) window.location.reload();
      }
    } catch {
      announce(
        "Не удалось изменить избранное. Обновите страницу и попробуйте снова.",
      );
      button.title = "Не удалось сохранить. Попробуйте снова.";
    } finally {
      button.disabled = false;
    }
  });
}
for (const select of document.querySelectorAll("[data-autosubmit]"))
  select.addEventListener("change", () => select.form.requestSubmit());
for (const button of document.querySelectorAll("[data-photo]"))
  button.addEventListener("click", () => {
    const photo = document.getElementById("main-photo");
    if (photo) photo.src = button.dataset.photo;
  });
const filterPanel = document.querySelector(".filter-panel");
if (filterPanel && window.matchMedia("(max-width: 700px)").matches)
  filterPanel.open = false;
