/* Progressively enhanced messenger: normal links and POST forms remain usable without JS. */
(() => {
  if (!document.querySelector("[data-messenger]")) return;
  const drafts = new Map();
  const pending = new Set();
  let cursor = 0;
  let readCursor = 0;
  let reading = false;
  let shell,
    historyBox,
    controller,
    navigation,
    busy = false,
    filter = "all",
    search = "";
  const csrf = () => shell.querySelector("[name=csrfmiddlewaretoken]")?.value;
  const endpoint = () => `/api/v1/conversations/${historyBox.dataset.chat}/`;
  const nearBottom = () =>
    !historyBox ||
    historyBox.scrollHeight - historyBox.scrollTop - historyBox.clientHeight <
      90;
  const draftKey = () => `${shell.dataset.user}:${historyBox?.dataset.chat}`;
  const grow = (textarea) => {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + "px";
  };
  const request = async (url, options = {}, signal = controller.signal) => {
    const response = await fetch(url, {
      credentials: "same-origin",
      signal,
      ...options,
    });
    if (!response.ok || response.redirected) throw new Error("request");
    return response;
  };
  function applyFilter() {
    let visible = 0;
    shell.querySelectorAll("[data-thread-search]").forEach((row) => {
      row.hidden =
        !row.dataset.threadSearch
          .toLocaleLowerCase("ru")
          .includes(search.toLocaleLowerCase("ru")) ||
        (filter === "unread" && !Number(row.dataset.unread));
      if (!row.hidden) visible++;
    });
    shell.querySelector("[data-search-empty]").hidden =
      visible > 0 || !shell.querySelector("[data-thread-search]");
    shell.querySelectorAll("[data-thread-filter]").forEach((button) => {
      const active = button.dataset.threadFilter === filter;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }
  function setup() {
    controller?.abort();
    controller = new AbortController();
    busy = false;
    reading = false;
    shell = document.querySelector("[data-messenger]");
    historyBox = shell.querySelector("[data-history]");
    shell.querySelector("[data-thread-search-input]").value = search;
    applyFilter();
    const textarea = shell.querySelector("[data-composer] textarea");
    if (textarea) {
      if (drafts.has(draftKey())) textarea.value = drafts.get(draftKey());
      grow(textarea);
      shell.querySelector("[data-composer] button").disabled =
        pending.has(draftKey());
      cursor = Math.max(
        0,
        ...[...historyBox.querySelectorAll("[data-message-id]")].map((row) =>
          Number(row.dataset.messageId),
        ),
      );
      readCursor = cursor; // Opening the HTML conversation marks existing messages read.
      historyBox.scrollTop = historyBox.scrollHeight;
      historyBox.addEventListener(
        "scroll",
        () => {
          if (nearBottom()) {
            shell.querySelector("[data-jump-bottom]").hidden = true;
            markRead().catch(() => {});
          }
        },
        { passive: true, signal: controller.signal },
      );
    }
  }
  async function navigate(url, push = true) {
    if (historyBox)
      drafts.set(
        draftKey(),
        shell.querySelector("[data-composer] textarea").value,
      );
    navigation?.abort();
    navigation = new AbortController();
    const navigationSignal = navigation.signal;
    controller.abort();
    shell.setAttribute("aria-busy", "true");
    try {
      const response = await request(
        url,
        { headers: { "X-Messenger-Request": "true" } },
        navigation.signal,
      );
      const doc = new DOMParser().parseFromString(
        await response.text(),
        "text/html",
      );
      if (navigationSignal.aborted) return;
      const next = doc.querySelector("[data-messenger]");
      if (!next) throw new Error("fragment");
      shell.replaceWith(next);
      if (push) window.history.pushState({}, "", url);
      setup();
      document.title = historyBox
        ? "Переписка — ДоскаСВФУ"
        : "Сообщения — ДоскаСВФУ";
      if (historyBox && matchMedia("(min-width:701px)").matches)
        shell.querySelector("textarea").focus({ preventScroll: true });
    } catch (error) {
      if (error.name !== "AbortError") window.location.assign(url);
    }
  }
  async function markRead() {
    if (!historyBox || document.hidden || !nearBottom() || reading) return;
    const latestIncoming = Math.max(
      0,
      ...[
        ...historyBox.querySelectorAll(".messenger-message:not(.is-own)"),
      ].map((row) => Number(row.dataset.messageId)),
    );
    if (latestIncoming <= readCursor) return;
    const expectedHistory = historyBox;
    reading = true;
    try {
      await request(endpoint() + "read/", {
        method: "POST",
        headers: { "X-CSRFToken": csrf() },
      });
      if (historyBox === expectedHistory) readCursor = latestIncoming;
    } finally {
      if (historyBox === expectedHistory) reading = false;
    }
  }
  function appendMessage(message) {
    if (historyBox.querySelector(`[data-message-id="${message.id}"]`)) return;
    const own = String(message.sender.id) === shell.dataset.user;
    const stick = nearBottom();
    const date = new Date(message.created_at);
    const day = date.toLocaleDateString("en-CA", {
      timeZone: shell.dataset.timezone,
    });
    const row = document.createElement("div");
    row.className = "messenger-message" + (own ? " is-own" : "");
    row.dataset.messageId = message.id;
    row.dataset.day = day;
    const bubble = document.createElement("div");
    bubble.className = "messenger-bubble";
    const content = document.createElement("p");
    content.textContent = message.text;
    const meta = document.createElement("small");
    const time = document.createElement("time");
    time.dateTime = message.created_at;
    time.textContent = new Date(message.created_at).toLocaleTimeString(
      "ru-RU",
      { hour: "2-digit", minute: "2-digit", timeZone: shell.dataset.timezone },
    );
    meta.append(time);
    if (own) {
      const delivery = document.createElement("span");
      delivery.dataset.delivery = "";
      delivery.textContent = message.read_at ? "Прочитано" : "Отправлено";
      meta.append(delivery);
    }
    bubble.append(content, meta);
    row.append(bubble);
    // Polling and a POST may finish in either order. Keep the message order stable.
    const next = [...historyBox.querySelectorAll("[data-message-id]")].find(
      (item) => Number(item.dataset.messageId) > message.id,
    );
    historyBox.insertBefore(row, next || null);
    refreshDates();
    if (stick || own) historyBox.scrollTop = historyBox.scrollHeight;
    else shell.querySelector("[data-jump-bottom]").hidden = false;
  }
  function refreshDates() {
    historyBox
      .querySelectorAll(".message-date")
      .forEach((item) => item.remove());
    let previousDay = null;
    for (const row of historyBox.querySelectorAll("[data-message-id]")) {
      if (row.dataset.day !== previousDay) {
        const divider = document.createElement("div");
        divider.className = "message-date";
        divider.textContent = new Date(
          row.querySelector("time").dateTime,
        ).toLocaleDateString("ru-RU", {
          day: "numeric",
          month: "short",
          year: "numeric",
          timeZone: shell.dataset.timezone,
        });
        row.before(divider);
        previousDay = row.dataset.day;
      }
    }
  }
  async function sidebar() {
    const expectedShell = shell;
    const active = historyBox?.dataset.chat || "";
    const response = await request(
      shell.dataset.sidebarUrl + "?active=" + active,
    );
    const data = await response.json();
    if (shell !== expectedShell) return;
    shell.querySelector("[data-thread-list]").innerHTML = data.html;
    shell.querySelector("[data-thread-count]").textContent = data.count;
    shell.querySelector("[data-unread-threads]").textContent =
      data.unread_threads;
    for (const id of data.read_ids) {
      const delivery = historyBox?.querySelector(
        `[data-message-id="${id}"] [data-delivery]`,
      );
      if (delivery) delivery.textContent = "Прочитано";
    }
    const nav = document.querySelector(
      '.desktop-nav a[aria-label="Сообщения"]',
    );
    let badge = nav.querySelector(".notification-count");
    if (data.unread_total && !badge) {
      badge = document.createElement("span");
      badge.className = "notification-count";
      nav.append(badge);
    }
    if (badge) {
      badge.textContent = data.unread_total;
      badge.hidden = !data.unread_total;
    }
    const mobileLabel = document.querySelector(
      '.mobile-nav a[href="/messages/"] span',
    );
    if (mobileLabel)
      mobileLabel.textContent =
        "Сообщения" + (data.unread_total ? " · " + data.unread_total : "");
    applyFilter();
  }
  async function poll() {
    if (document.hidden || busy || shell.getAttribute("aria-busy") === "true")
      return;
    busy = true;
    const signal = controller.signal;
    try {
      if (historyBox) {
        let url = endpoint() + "messages/?after=" + cursor;
        while (url) {
          const data = await (await request(url, {}, signal)).json();
          if (signal.aborted) return;
          data.results.forEach(appendMessage);
          for (const message of data.results)
            cursor = Math.max(cursor, message.id);
          url = data.next ? new URL(data.next, location.origin) : null;
          if (url && url.origin !== location.origin) throw new Error("origin");
        }
        await markRead();
        shell.querySelector("[data-connection-status]").textContent =
          "Сообщения обновляются автоматически";
      }
      await sidebar();
    } catch (error) {
      if (!signal.aborted) {
        const status = shell.querySelector("[data-connection-status]");
        if (status)
          status.textContent =
            "Нет связи. Переписка обновится после подключения.";
      }
    } finally {
      if (!signal.aborted) busy = false;
    }
  }
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-thread-link]");
    if (
      link &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.shiftKey &&
      event.button === 0
    ) {
      event.preventDefault();
      navigate(link.href);
    }
    const tab = event.target.closest("[data-thread-filter]");
    if (tab) {
      filter = tab.dataset.threadFilter;
      applyFilter();
    }
    if (event.target.closest("[data-jump-bottom]")) {
      historyBox.scrollTop = historyBox.scrollHeight;
      shell.querySelector("[data-jump-bottom]").hidden = true;
      markRead().catch(() => {});
    }
  });
  document.addEventListener("input", (event) => {
    if (event.target.matches("[data-thread-search-input]")) {
      search = event.target.value;
      applyFilter();
    }
    if (event.target.matches("[data-composer] textarea")) {
      grow(event.target);
      drafts.set(draftKey(), event.target.value);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (
      event.target.matches("[data-composer] textarea") &&
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.isComposing &&
      matchMedia("(min-width:701px)").matches
    ) {
      event.preventDefault();
      event.target.form.requestSubmit();
    }
  });
  document.addEventListener("submit", async (event) => {
    if (!event.target.matches("[data-composer]")) return;
    event.preventDefault();
    const form = event.target,
      textarea = form.querySelector("textarea"),
      button = form.querySelector("button");
    if (button.disabled) return;
    const value = textarea.value.trim();
    if (!value) return;
    const currentShell = shell,
      key = draftKey(),
      url = endpoint() + "messages/";
    button.disabled = true;
    pending.add(key);
    currentShell.querySelector("[data-chat-error]").textContent = "";
    // A send is allowed to finish when switching chats; its draft is cleared only after success.
    try {
      const response = await request(
        url,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf(),
          },
          body: JSON.stringify({ text: value }),
        },
        null,
      );
      const message = await response.json();
      if (drafts.get(key)?.trim() === value) drafts.delete(key);
      if (draftKey() === key) {
        appendMessage(message);
        const activeTextarea = shell.querySelector("[data-composer] textarea");
        if (activeTextarea.value.trim() === value) {
          activeTextarea.value = "";
          grow(activeTextarea);
        }
        activeTextarea.focus({ preventScroll: true });
        sidebar().catch(() => {});
      }
    } catch {
      currentShell.querySelector("[data-chat-error]").textContent =
        "Не удалось отправить. Текст сохранён — попробуйте ещё раз.";
    } finally {
      pending.delete(key);
      button.disabled = false;
      if (draftKey() === key)
        shell.querySelector("[data-composer] button").disabled = false;
    }
  });
  window.addEventListener("popstate", () => navigate(location.href, false));
  document.addEventListener("visibilitychange", poll);
  setup();
  setInterval(poll, 6000);
  poll();
})();
