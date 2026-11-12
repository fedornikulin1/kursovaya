(() => {
  const root = document.querySelector("[data-saved-searches]");
  if (!root) return;

  const content = root.querySelector("[data-saved-search-content]");
  const tray = root.querySelector("[data-saved-search-undo]");
  const status = root.querySelector("[data-undo-status]");
  const undo = root.querySelector("[data-undo-button]");
  const fuse = tray.querySelector(".saved-search-fuse");
  let pending = false;
  let timer;
  let fuseAnimation;
  let restoreData;

  function stopCountdown() {
    clearTimeout(timer);
    fuseAnimation?.cancel();
    fuse.hidden = true;
  }

  function showStatus(message) {
    tray.hidden = false;
    status.textContent = message;
  }

  async function post(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { Accept: "application/json" },
      body,
    });
    if (response.redirected) throw new Error("Войдите снова, чтобы продолжить.");
    if (!response.headers.get("content-type")?.includes("application/json")) {
      throw new Error("Обновите страницу и попробуйте снова.");
    }
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Попробуйте ещё раз.");
    return payload;
  }

  root.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!form.matches("[data-saved-search-delete]")) return;
    event.preventDefault();
    if (pending) return;
    pending = true;
    const button = form.querySelector("button");
    const keyboard = button.matches(":focus-visible");
    const body = new FormData(form);
    button.disabled = true;
    try {
      const result = await post(form.action, body);
      content.innerHTML = result.html;
      stopCountdown();
      body.set("undo_token", result.undo_token);
      restoreData = body;
      showStatus("Поиск удалён.");
      undo.hidden = false;
      if (keyboard) undo.focus();
      const duration = result.undo_seconds * 1000;
      if (!document.body.classList.contains("reduce-motion") &&
          !matchMedia("(prefers-reduced-motion: reduce)").matches) {
        fuse.hidden = false;
        fuseAnimation = fuse.animate(
          [{ transform: "scaleX(1)" }, { transform: "scaleX(0)" }],
          { duration, fill: "forwards" },
        );
      }
      timer = setTimeout(() => {
        if (document.activeElement === undo) {
          content.querySelector("a, button")?.focus();
        }
        restoreData = null;
        tray.hidden = true;
        undo.hidden = true;
        stopCountdown();
      }, duration);
    } catch (error) {
      showStatus(`Не удалось удалить поиск. ${error.message}`);
    } finally {
      pending = false;
      button.disabled = false;
    }
  });

  undo.addEventListener("click", async () => {
    if (pending || !restoreData) return;
    pending = true;
    undo.disabled = true;
    try {
      const result = await post(root.dataset.restoreUrl, restoreData);
      stopCountdown();
      content.innerHTML = result.html;
      content.querySelector(`[data-saved-search-id="${result.restored_id}"] a`)?.focus();
      showStatus("Поиск восстановлен.");
      undo.hidden = true;
      restoreData = null;
      timer = setTimeout(() => { tray.hidden = true; }, 2500);
    } catch (error) {
      showStatus(`Не удалось восстановить поиск. ${error.message}`);
    } finally {
      pending = false;
      undo.disabled = false;
    }
  });
})();
