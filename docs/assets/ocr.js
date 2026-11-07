(() => {
  "use strict";
  function revealTarget() {
    const target = document.getElementById(location.hash.slice(1));
    if (!target) return;
    const redirect = target.querySelector("[data-ocr-redirect]");
    if (redirect) {
      location.replace(redirect.href);
      return;
    }
    let module = target.closest("details.ocr-module");
    // Material links body-text matches to the surrounding directory heading.
    if (!module) {
      const query = new URLSearchParams(location.search).get("h") || "";
      const terms = query.toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu) || [];
      if (terms.length) {
        const matches = [...document.querySelectorAll("details.ocr-module")].filter(item =>
          terms.every(term => item.textContent.toLocaleLowerCase().includes(term))
        );
        matches.forEach(item => { item.open = true; });
        module = matches[0];
      }
    }
    if (module) {
      module.open = true;
      requestAnimationFrame(() => module.scrollIntoView({ block: "start" }));
    }
  }
  revealTarget();
  window.addEventListener("hashchange", revealTarget);
})();
