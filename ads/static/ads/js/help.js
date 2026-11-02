(() => {
  const input = document.querySelector("[data-faq-search]");
  if (!input) return;
  let topic = "all";
  const filter = () => {
    const query = input.value.trim().toLocaleLowerCase("ru");
    let visible = 0;
    document.querySelectorAll("[data-faq]").forEach((item) => {
      item.hidden =
        (topic !== "all" && item.dataset.topic !== topic) ||
        !item.textContent.toLocaleLowerCase("ru").includes(query);
      if (!item.hidden) visible++;
    });
    document.querySelector("[data-faq-empty]").hidden = visible > 0;
  };
  input.addEventListener("input", filter);
  document.querySelectorAll("[data-faq-topic]").forEach((button) =>
    button.addEventListener("click", () => {
      topic = button.dataset.faqTopic;
      document.querySelectorAll("[data-faq-topic]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      filter();
    }),
  );
})();
