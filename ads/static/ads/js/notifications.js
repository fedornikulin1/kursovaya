(() => {
  const bell = document.querySelector("[data-notification-count]");
  if (!bell) return;
  const badge = bell.querySelector("[data-notification-badge]");
  let loading = false;

  async function refresh() {
    if (document.hidden || loading) return;
    loading = true;
    try {
      const response = await fetch(bell.dataset.notificationCount, {
        headers: { Accept: "application/json" },
        redirect: "error",
        signal: AbortSignal.timeout(8000),
      });
      if (!response.ok) return;
      const { unread } = await response.json();
      badge.textContent = unread > 99 ? "99+" : String(unread);
      badge.hidden = unread === 0;
      bell.setAttribute("aria-label", unread ? `Уведомления, непрочитанных ${unread}` : "Уведомления");
    } catch {
      // Keep the most recent count until the next successful check.
    } finally {
      loading = false;
    }
  }

  refresh();
  document.addEventListener("visibilitychange", refresh);
  window.setInterval(refresh, 45000);
})();
