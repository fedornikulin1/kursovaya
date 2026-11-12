for (const field of document.querySelectorAll("[data-profile-image]")) {
  const input = field.querySelector('input[type="file"]');
  const clear = field.querySelector("[data-image-clear]");
  const reset = field.querySelector("[data-image-reset]");
  const preview = field.querySelector("[data-image-preview]");
  const fallback = field.querySelector("[data-image-fallback]");
  const saved = preview.getAttribute("src");
  let objectUrl;

  function refresh() {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    const file = input.files[0];
    objectUrl = file ? URL.createObjectURL(file) : null;
    const src = objectUrl || (!clear?.checked && saved);
    if (src) preview.src = src;
    else preview.removeAttribute("src");
    preview.hidden = !src;
    if (fallback) fallback.hidden = Boolean(src);
    reset.hidden = !file;
  }

  input.addEventListener("change", () => {
    if (input.files.length && clear) clear.checked = false;
    refresh();
  });
  clear?.addEventListener("change", () => {
    if (clear.checked) input.value = "";
    refresh();
  });
  reset.addEventListener("click", () => {
    input.value = "";
    refresh();
    input.focus();
  });
  refresh();
}
