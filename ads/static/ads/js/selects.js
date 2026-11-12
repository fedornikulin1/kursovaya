/* Accessible progressive enhancement of native selects. Native forms remain the source of truth. */
(() => {
  let widgets = [];
  let generatedId = 0;
  function enhanceSelects(root) {
    widgets = widgets.filter((widget) => widget.wrapper.isConnected);
    for (const select of root.querySelectorAll("select")) {
      // Keep the radio-like choices and explicit native selects in their own controls.
      if (
        select.multiple ||
        select.hasAttribute("data-jelly-select") ||
        select.hasAttribute("data-native-select")
      )
        continue;
      if (select.classList.contains("enhanced-select")) continue;
      if (!select.options.length) continue;
      // Legacy Django forms can still render a dashed empty choice. Keep its
      // empty value (and validation), but give it a useful visible label.
      for (const option of select.options) {
        if (option.value === "" && /^\s*[-–—]+\s*$/.test(option.textContent)) {
          option.textContent = select.dataset.emptyLabel ||
            (select.required ? "Выберите вариант" : "Не выбрано");
        }
      }
      if (!select.id) select.id = `site-select-${++generatedId}`;
      const wrapper = document.createElement("div");
      wrapper.className = "custom-select";
      select.before(wrapper);
      wrapper.append(select);
      const trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "custom-select-trigger";
      trigger.id = select.id + "-trigger";
      trigger.setAttribute("role", "combobox");
      trigger.setAttribute("aria-haspopup", "listbox");
      trigger.setAttribute("aria-expanded", "false");
      const label = document.querySelector(`label[for="${select.id}"]`);
      if (label) {
        label.id = select.id + "-label";
        trigger.setAttribute(
          "aria-labelledby",
          label.id + " " + select.id + "-value",
        );
        label.htmlFor = trigger.id;
      } else {
        const wrappedLabel = select.closest("label");
        if (wrappedLabel)
          trigger.setAttribute(
            "aria-label",
            wrappedLabel.querySelector(".sr-only")?.textContent.trim() ||
              "Выбрать вариант",
          );
      }
      const value = document.createElement("span");
      value.id = select.id + "-value";
      const chevron = document.createElement("span");
      chevron.className = "select-chevron";
      chevron.setAttribute("aria-hidden", "true");
      trigger.append(value, chevron);
      const list = document.createElement("div");
      list.className = "custom-select-list";
      list.id = select.id + "-list";
      list.setAttribute("role", "listbox");
      list.setAttribute("aria-labelledby", label ? label.id : trigger.id);
      list.hidden = true;
      trigger.setAttribute("aria-controls", list.id);
      const highlight = document.createElement("span");
      highlight.className = "custom-select-glide";
      highlight.setAttribute("aria-hidden", "true");
      list.append(highlight);
      let active = Math.max(0, select.selectedIndex);
      const placeHighlight = () => {
        const option = options[active];
        highlight.style.height = `${option.offsetHeight}px`;
        highlight.style.transform = `translateY(${option.offsetTop}px)`;
      };
      const options = [...select.options].map((option, index) => {
        const item = document.createElement("div");
        item.id = select.id + "-option-" + index;
        item.className = "custom-select-option";
        item.setAttribute("role", "option");
        item.textContent = option.textContent;
        // Keep focus on the combobox until click chooses the option.
        item.addEventListener("pointerdown", (event) => event.preventDefault());
        item.addEventListener("click", () => choose(index));
        item.addEventListener("pointerenter", (event) => {
          if (event.pointerType === "touch") return;
          active = index;
          update();
        });
        list.append(item);
        return item;
      });
      const update = () => {
        value.textContent =
          select.options[select.selectedIndex]?.textContent ??
          "Выберите вариант";
        options.forEach((item, index) => {
          item.setAttribute(
            "aria-selected",
            String(index === select.selectedIndex),
          );
          item.classList.toggle("is-focused", index === active);
        });
        trigger.setAttribute(
          "aria-activedescendant",
          options[active]?.id ?? "",
        );
        if (!list.hidden) placeHighlight();
      };
      const close = () => {
        list.hidden = true;
        wrapper.append(list);
        list.removeAttribute("style");
        trigger.setAttribute("aria-expanded", "false");
        wrapper.classList.remove("is-open");
      };
      const open = () => {
        widgets.forEach((widget) => widget.close());
        active = Math.max(0, select.selectedIndex);
        update();
        // Render the menu at page level so scrollable forms cannot clip its options.
        document.body.append(list);
        list.hidden = false;
        const rect = trigger.getBoundingClientRect();
        const desired = Math.min(282, list.scrollHeight + 2);
        const below = window.innerHeight - rect.bottom - 10;
        const above = rect.top - 10;
        const openAbove = below < desired && above > below;
        const height = Math.max(
          60,
          Math.min(desired, openAbove ? above : below),
        );
        list.style.position = "fixed";
        list.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - rect.width - 8))}px`;
        list.style.right = "auto";
        list.style.width = `${Math.min(rect.width, window.innerWidth - 16)}px`;
        list.style.maxHeight = `${height}px`;
        list.style.top = `${openAbove ? rect.top - height - 7 : rect.bottom + 7}px`;
        list.style.zIndex = "10000";
        placeHighlight();
        trigger.setAttribute("aria-expanded", "true");
        wrapper.classList.add("is-open");
        list.scrollTop = Math.max(0, options[active].offsetTop - height / 2);
      };
      function choose(index) {
        select.selectedIndex = index;
        active = index;
        update();
        close();
        trigger.focus();
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      trigger.addEventListener("click", () => (list.hidden ? open() : close()));
      let search = "";
      let searchTimer;
      trigger.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          close();
          return;
        }
        if (event.key === "Tab") {
          close();
          return;
        }
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault();
          if (list.hidden) open();
          else choose(active);
          return;
        }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          if (list.hidden) open();
          if (event.key === "Home") active = 0;
          else if (event.key === "End") active = options.length - 1;
          else
            active =
              (active + (event.key === "ArrowDown" ? 1 : -1) + options.length) %
              options.length;
          update();
          list.scrollTop = Math.max(
            0,
            options[active].offsetTop - list.clientHeight / 2,
          );
        } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
          event.preventDefault();
          if (list.hidden) open();
          search += event.key.toLocaleLowerCase("ru");
          clearTimeout(searchTimer);
          searchTimer = setTimeout(() => {
            search = "";
          }, 600);
          const match = [...select.options].findIndex((option) =>
            option.textContent
              .trim()
              .toLocaleLowerCase("ru")
              .startsWith(search),
          );
          if (match >= 0) {
            active = match;
            update();
            list.scrollTop = Math.max(
              0,
              options[active].offsetTop - list.clientHeight / 2,
            );
          }
        }
      });
      select.addEventListener("change", () => {
        active = Math.max(0, select.selectedIndex);
        update();
      });
      select.addEventListener("invalid", (event) => {
        event.preventDefault();
        trigger.focus();
        open();
      });
      wrapper.addEventListener("focusout", (event) => {
        if (!wrapper.contains(event.relatedTarget)) close();
      });
      wrapper.append(trigger, list);
      select.classList.add("enhanced-select");
      select.tabIndex = -1;
      select.setAttribute("aria-hidden", "true");
      update();
      widgets.push({ wrapper, list, close });
    }
  }
  window.enhanceSiteSelects = enhanceSelects;
  enhanceSelects(document.querySelector("main") || document);
  document.addEventListener("click", (event) => {
    widgets.forEach((widget) => {
      if (
        !widget.wrapper.contains(event.target) &&
        !widget.list.contains(event.target)
      )
        widget.close();
    });
  });
  document.addEventListener(
    "scroll",
    (event) => {
      widgets.forEach((widget) => {
        if (!widget.list.hidden && !widget.list.contains(event.target))
          widget.close();
      });
    },
    true,
  );
  window.addEventListener("resize", () =>
    widgets.forEach((widget) => widget.close()),
  );
})();
