(() => {
  const menu = document.querySelector("[data-account-menu]");
  if (menu) {
    const trigger = menu.querySelector("summary");
    menu.addEventListener("toggle", () =>
      trigger.setAttribute("aria-expanded", String(menu.open)),
    );
    document.addEventListener("click", (event) => {
      if (!menu.contains(event.target)) menu.open = false;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menu.open) {
        menu.open = false;
        trigger.focus();
      }
    });
  }

  const navigation = document.querySelector("[data-header-nav]");
  if (navigation) {
    const underline = navigation.querySelector(".header-nav-underline");
    const current = navigation.querySelector("a[aria-current]");
    let hovered = null;

    const placeUnderline = () => {
      const target = navigation.querySelector("a:focus-visible") || hovered || current;
      const label = target?.querySelector(".header-nav-label");
      const bounds = (label?.offsetWidth ? label : target)?.getBoundingClientRect();
      navigation.classList.toggle("has-underline-target", Boolean(bounds?.width));
      if (!bounds?.width) return;
      const offset = bounds.left - navigation.getBoundingClientRect().left;
      underline.style.setProperty("--underline-offset", `${offset}px`);
      underline.style.setProperty("--underline-width", `${bounds.width}px`);
    };

    navigation.querySelectorAll("a").forEach((link) => {
      link.addEventListener("pointerenter", (event) => {
        if (event.pointerType === "touch") return;
        hovered = link;
        placeUnderline();
      });
    });
    navigation.addEventListener("pointerleave", () => {
      hovered = null;
      placeUnderline();
    });
    navigation.addEventListener("focusin", placeUnderline);
    navigation.addEventListener("focusout", () => queueMicrotask(placeUnderline));
    new ResizeObserver(placeUnderline).observe(navigation);
    navigation.classList.add("has-underline");
    placeUnderline();
  }

  const header = document.querySelector(".site-header");
  if (header) {
    // Leave the header in document flow; translating it never shifts page content.
    let lastY = Math.max(0, window.scrollY),
      direction = 0,
      distance = 0,
      scheduled = false;
    const showHeader = () => header.classList.remove("is-scroll-hidden");
    const resetDirection = () => {
      lastY = Math.max(0, window.scrollY);
      direction = 0;
      distance = 0;
    };
    const updateHeader = () => {
      scheduled = false;
      const maximum = Math.max(
        0,
        document.documentElement.scrollHeight - innerHeight,
      );
      const y = Math.max(0, Math.min(window.scrollY, maximum));
      const delta = y - lastY;
      lastY = y;
      const stripHeight =
        document.querySelector(".university-strip")?.offsetHeight || 0;
      header.classList.toggle("is-scrolled", y > stripHeight);
      if (
        y <= header.offsetHeight + stripHeight ||
        menu?.open ||
        header.querySelector(":focus-visible")
      ) {
        showHeader();
        direction = 0;
        distance = 0;
        return;
      }
      if (!delta) return;
      const nextDirection = Math.sign(delta);
      distance =
        nextDirection === direction
          ? distance + Math.abs(delta)
          : Math.abs(delta);
      direction = nextDirection;
      if (direction < 0 && distance >= 8) showHeader();
      if (direction > 0 && distance >= 18)
        header.classList.add("is-scroll-hidden");
    };
    window.addEventListener(
      "scroll",
      () => {
        if (!scheduled) {
          scheduled = true;
          requestAnimationFrame(updateHeader);
        }
      },
      { passive: true },
    );
    header.addEventListener("focusin", () => {
      showHeader();
      resetDirection();
    });
    menu?.addEventListener("toggle", () => {
      if (menu.open) {
        showHeader();
        resetDirection();
      }
    });
    window.addEventListener("resize", () => {
      showHeader();
      resetDirection();
      updateHeader();
    });
    window.addEventListener("pageshow", () => {
      showHeader();
      resetDirection();
    });
    updateHeader();
  }
})();
