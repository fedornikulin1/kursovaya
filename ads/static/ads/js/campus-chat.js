(() => {
  const chat = document.querySelector("[data-campus-chat]");
  if (!chat) return;

  // Keep the selected room visible without moving the page itself.
  const activeRoom = chat.querySelector('.campus-chat-room[aria-current="page"]');
  const mobileRooms = matchMedia("(max-width: 760px)").matches;
  const roomList = chat.querySelector(mobileRooms ? ".campus-chat-rooms" : ".campus-chat-room-list");
  if (activeRoom && roomList?.contains(activeRoom)) {
    const item = activeRoom.getBoundingClientRect();
    const viewport = roomList.getBoundingClientRect();
    if (mobileRooms) roomList.scrollLeft += item.left - viewport.left;
    else if (item.bottom > viewport.bottom) roomList.scrollTop += item.bottom - viewport.bottom;
  }
  const feed = chat.querySelector("[data-campus-feed]");
  let highlighted;
  let highlightTimer;
  chat.addEventListener("click", (event) => {
    const quote = event.target.closest("[data-campus-quote]");
    if (!quote || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const original = document.getElementById(`campus-message-${quote.dataset.campusQuote}`);
    if (!original || !feed.contains(original)) return;
    event.preventDefault();
    highlighted?.classList.remove("is-highlighted");
    highlighted = original;
    clearTimeout(highlightTimer);
    original.classList.add("is-highlighted");
    original.scrollIntoView({ block: "nearest" });
    highlightTimer = setTimeout(() => original.classList.remove("is-highlighted"), 2200);
  });
  if (!chat.dataset.feedUrl) {
    const original = document.getElementById(location.hash.slice(1));
    if (original && feed.contains(original)) original.scrollIntoView({ block: "nearest" });
    return;
  }

  const messages = chat.querySelector("[data-campus-messages]");
  const composer = chat.querySelector("[data-campus-composer]");
  const body = composer.querySelector("[data-campus-body]");
  const reply = composer.querySelector("[data-campus-reply-input]");
  const preview = composer.querySelector("[data-campus-reply-preview]");
  const replyName = preview.querySelector("[data-campus-reply-name]");
  const replyText = preview.querySelector("[data-campus-reply-text]");
  const jump = chat.querySelector("[data-campus-jump]");
  const status = chat.querySelector("[data-campus-status]");
  const sendStatus = chat.querySelector("[data-campus-send-status]");
  const errors = composer.querySelector("[data-campus-errors]");
  const sendButton = composer.querySelector('[type="submit"]');
  const empty = chat.querySelector("[data-campus-empty]");
  let watchOffset = 0;
  let latestId = chat.dataset.latestId || "0";
  let timer;

  const atBottom = () => feed.scrollHeight - feed.scrollTop - feed.clientHeight < 42;
  const showLatest = () => {
    feed.scrollTop = feed.scrollHeight;
    jump.hidden = true;
  };
  showLatest();
  jump.addEventListener("click", showLatest);
  feed.addEventListener("scroll", () => {
    if (atBottom()) jump.hidden = true;
  }, { passive: true });

  function setReply(target = "", author = "", excerpt = "") {
    reply.value = target;
    preview.hidden = !target;
    replyName.textContent = target ? `Ответ для ${author}` : "";
    replyText.textContent = excerpt;
  }

  chat.addEventListener("click", (event) => {
    const link = event.target.closest("[data-campus-reply], [data-campus-cancel-reply]");
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    setReply(link.dataset.campusReply, link.dataset.campusAuthor, link.dataset.campusExcerpt);
    if (link.dataset.campusReply) composer.querySelector('[name="kind"][value="general"]').checked = true;
    body.focus();
  });

  function appendMessages(html) {
    if (!html) return;
    const follow = atBottom();
    const fragment = document.createElement("template");
    fragment.innerHTML = html;
    const received = [...fragment.content.children];
    const existing = [...messages.children];
    let position = 0;
    let added = false;
    for (const message of received) {
      if (document.getElementById(message.id)) continue;
      const id = BigInt(message.dataset.campusMessage);
      while (existing[position] && BigInt(existing[position].dataset.campusMessage) < id) {
        position++;
      }
      messages.insertBefore(message, existing[position] || null);
      added = true;
    }
    if (added) {
      empty.hidden = true;
      if (follow) showLatest();
      else jump.hidden = false;
    }
    return received.at(-1)?.dataset.campusMessage;
  }

  composer.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (sendButton.disabled) return;
    const draft = body.value;
    const replyTarget = reply.value;
    const data = new FormData(composer);
    errors.hidden = true;
    errors.textContent = "";
    sendStatus.textContent = "Отправляем…";
    sendButton.disabled = true;
    try {
      const response = await fetch(composer.action, {
        method: "POST",
        headers: { Accept: "application/json" },
        body: data,
        signal: AbortSignal.timeout(10000),
      });
      if (response.redirected) {
        errors.textContent = "Войдите снова, чтобы продолжить.";
        return;
      }
      if (![201, 400, 413, 429].includes(response.status)) throw new Error("Campus chat send failed");
      const payload = await response.json();
      if (response.status === 413 || response.status === 429) {
        errors.textContent = payload.detail;
        return;
      }
      if (response.status === 400) {
        errors.textContent = Object.values(payload.errors).flat().map((error) => error.message).join(" ");
        return;
      }
      // Leave the polling cursor alone so messages sent before ours still arrive.
      appendMessages(payload.html);
      if (body.value === draft && reply.value === replyTarget) {
        body.value = "";
        setReply();
      }
      sendStatus.textContent = payload.html ? "" : "Отправлено в обсуждения.";
    } catch {
      errors.textContent = "Не удалось подтвердить отправку. Проверьте ленту и попробуйте снова.";
    } finally {
      sendButton.disabled = false;
      errors.hidden = !errors.textContent;
      if (sendStatus.textContent === "Отправляем…") sendStatus.textContent = "";
    }
  });

  async function poll() {
    if (document.hidden) {
      timer = setTimeout(poll, 5000);
      return;
    }
    let delay = 5000;
    try {
      const url = new URL(chat.dataset.feedUrl, window.location.origin);
      url.searchParams.set("after", latestId);
      const current = [...messages.querySelectorAll('[data-wanted-state="open"]')]
        .map((badge) => badge.closest("[data-campus-message]"));
      if (current.length) {
        if (watchOffset >= current.length) watchOffset = 0;
        const watched = current.slice(watchOffset, watchOffset + 50);
        url.searchParams.set("watch", watched.map((row) => row.dataset.campusMessage).join(","));
        watchOffset += watched.length;
      }
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
      if (response.redirected) {
        status.textContent = "Войдите снова, чтобы продолжить.";
        return;
      }
      if (!response.ok) throw new Error("Campus chat feed unavailable");
      const { html, has_more: hasMore, removed = [], closed_requests: closedRequests = {} } = await response.json();
      status.textContent = "";
      for (const id of removed) {
        const row = document.getElementById(`campus-message-${id}`);
        if (row?.parentElement === messages) row.remove();
      }
      for (const [id, label] of Object.entries(closedRequests)) {
        const row = document.getElementById(`campus-message-${id}`);
        const badge = row?.querySelector("[data-wanted-state]");
        if (row?.parentElement !== messages || !badge) continue;
        badge.textContent = label;
        badge.dataset.wantedState = "closed";
        badge.classList.add("is-closed");
        row.querySelector("[data-wanted-action]")?.remove();
      }
      latestId = appendMessages(html) || latestId;
      empty.hidden = messages.childElementCount > 0;
      if (hasMore) delay = 100;
    } catch {
      status.textContent = "Не удалось обновить ленту. Повторяем…";
    }
    timer = setTimeout(poll, delay);
  }
  timer = setTimeout(poll, 5000);
  window.addEventListener("pagehide", () => clearTimeout(timer));
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) timer = setTimeout(poll, 5000);
  });
})();
