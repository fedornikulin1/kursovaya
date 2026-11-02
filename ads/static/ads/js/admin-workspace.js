(() => {
  const nav = document.querySelector("[data-admin-sections]");
  if (!nav) return;
  const media = matchMedia("(min-width:1100px)");
  const update = () => {
    nav.open = media.matches;
  };
  update();
  media.addEventListener("change", update);
})();
