/* One local date picker for every public form; submitted values stay ISO for Django. */
(() => {
  if (typeof flatpickr !== "function") return;

  function enhanceCalendars(root) {
    for (const input of root.querySelectorAll(
      'input[type="date"], input[type="datetime-local"]',
    )) {
      const withTime = input.type === "datetime-local";
      flatpickr(input, {
        locale: flatpickr.l10ns.ru,
        disableMobile: true,
        enableTime: withTime,
        time_24hr: true,
        minuteIncrement: 5,
        dateFormat: withTime ? "Y-m-d\\TH:i" : "Y-m-d",
        altInput: true,
        altInputClass: "campus-calendar-display",
        altFormat: withTime ? "d.m.Y H:i" : "d.m.Y",
        allowInput: false,
        onReady(_, __, picker) {
          picker.altInput.placeholder = withTime
            ? "Выберите дату и время"
            : "Выберите дату";
          if (input.id) {
            picker.altInput.id = `${input.id}-display`;
            const label = document.querySelector(`label[for="${input.id}"]`);
            if (label) label.htmlFor = picker.altInput.id;
            else
              picker.altInput.setAttribute(
                "aria-label",
                input.getAttribute("aria-label") || "Выбрать дату",
              );
          } else {
            picker.altInput.setAttribute(
              "aria-label",
              input.getAttribute("aria-label") || "Выбрать дату",
            );
          }
          input.addEventListener("invalid", (event) => {
            event.preventDefault();
            picker.altInput.focus();
            picker.open();
          });
        },
      });
    }
  }
  window.enhanceSiteCalendars = enhanceCalendars;
  window.destroySiteCalendars = (root) => {
    root
      .querySelectorAll(".flatpickr-input")
      .forEach((input) => input._flatpickr?.destroy());
  };
  enhanceCalendars(document.querySelector("main") || document);
})();
