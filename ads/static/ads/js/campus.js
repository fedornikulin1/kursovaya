/* Optional enhancements. All forms also submit normally with CSRF protection. */
(() => {
  const study = document.querySelector('[name="is_study"]');
  const settings = document.querySelector("[data-study-settings]");
  if (study && settings) {
    const update = () => {
      settings.hidden = !study.checked;
      const subject = settings.querySelector('[name="subject"]');
      if (subject) subject.required = study.checked;
    };
    study.addEventListener("change", update);
    update();
  }
  // The current dialog is replaced when switching conversations; delegate and rediscover it.
  document.addEventListener("input", (event) => {
    const panel = event.target.closest("[data-meeting-panel]");
    if (panel) panel.dataset.dirty = "true";
  });
  let polling = false;
  async function refreshMeeting() {
    const panel = document.querySelector("[data-meeting-panel]");
    if (
      !panel ||
      polling ||
      document.hidden ||
      panel.dataset.dirty ||
      panel.contains(document.activeElement)
    )
      return;
    polling = true;
    try {
      const response = await fetch(panel.dataset.meetingUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok || response.redirected) return;
      const data = await response.json();
      if (
        !panel.isConnected ||
        panel.dataset.dirty ||
        panel.contains(document.activeElement) ||
        data.revision === panel.dataset.revision
      )
        return;
      const parsed = new DOMParser().parseFromString(data.html, "text/html");
      const next = parsed.querySelector("[data-meeting-panel]");
      if (next) {
        next.open = panel.open;
        panel.replaceWith(next);
      }
    } catch {
      /* Keep the last known state during a temporary network failure. */
    } finally {
      polling = false;
    }
  }
  setInterval(refreshMeeting, 15000);
  document.addEventListener("visibilitychange", refreshMeeting);
})();
