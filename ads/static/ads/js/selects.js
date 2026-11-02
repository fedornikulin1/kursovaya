/* Accessible progressive enhancement of native selects. Native forms remain the source of truth. */
(() => {
  const widgets = [];
  for (const select of document.querySelectorAll("[data-pretty-select]")) {
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
    const label = document.querySelector('label[for="' + select.id + '"]');
    if (label) {
      label.id = select.id + "-label";
      trigger.setAttribute(
        "aria-labelledby",
        label.id + " " + select.id + "-value",
      );
      label.htmlFor = trigger.id;
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
    let active = select.selectedIndex;
    const options = [...select.options].map((option, index) => {
      const item = document.createElement("div");
      item.id = select.id + "-option-" + index;
      item.className = "custom-select-option";
      item.setAttribute("role", "option");
      item.textContent = option.textContent;
      // Keep focus on the combobox until click chooses the option.
      item.addEventListener("pointerdown", (event) => event.preventDefault());
      item.addEventListener("click", () => choose(index));
      list.append(item);
      return item;
    });
    const update = () => {
      value.textContent = select.options[select.selectedIndex].textContent;
      options.forEach((item, index) => {
        item.setAttribute(
          "aria-selected",
          String(index === select.selectedIndex),
        );
        item.classList.toggle("is-focused", index === active);
      });
      trigger.setAttribute("aria-activedescendant", options[active].id);
    };
    const close = () => {
      list.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
      wrapper.classList.remove("is-open");
    };
    const open = () => {
      widgets.forEach((widget) => widget.close());
      active = select.selectedIndex;
      update();
      list.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      wrapper.classList.add("is-open");
      options[active].scrollIntoView({ block: "nearest" });
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
        options[active].scrollIntoView({ block: "nearest" });
      } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        if (list.hidden) open();
        search += event.key.toLocaleLowerCase("ru");
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
          search = "";
        }, 600);
        const match = [...select.options].findIndex((option) =>
          option.textContent.trim().toLocaleLowerCase("ru").startsWith(search),
        );
        if (match >= 0) {
          active = match;
          update();
          options[active].scrollIntoView({ block: "nearest" });
        }
      }
    });
    select.addEventListener("change", () => {
      active = select.selectedIndex;
      update();
    });
    wrapper.addEventListener("focusout", (event) => {
      if (!wrapper.contains(event.relatedTarget)) close();
    });
    wrapper.append(trigger, list);
    select.classList.add("enhanced-select");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");
    update();
    widgets.push({ wrapper, close });
  }
  document.addEventListener("click", (event) => {
    widgets.forEach((widget) => {
      if (!widget.wrapper.contains(event.target)) widget.close();
    });
  });
})();
