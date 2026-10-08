(() => {
  "use strict";
  const KEY = "ai-fable-notes.progress.v1";
  const scriptUrl = document.currentScript.src;
  const siteBase = new URL("../", scriptUrl);
  const empty = () => ({ version: 1, lessons: {}, lastRead: null });
  const validId = id => typeof id === "string" && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id);
  function clean(value) {
    if (!value || value.version !== 1 || typeof value.lessons !== "object" || !value.lessons) throw new Error("进度文件格式不支持");
    const result = empty();
    for (const [id, item] of Object.entries(value.lessons)) {
      if (!validId(id) || !item || typeof item.completed !== "boolean") continue;
      result.lessons[id] = { completed: item.completed, scroll: Number.isFinite(item.scroll) ? Math.max(0, Math.min(item.scroll, 10000000)) : 0 };
    }
    if (value.lastRead && validId(value.lastRead.id)) result.lastRead = { id: value.lastRead.id };
    return result;
  }
  let state = empty();
  function notify(message) {
    let status = document.getElementById("storage-warning");
    if (!status) {
      status = document.createElement("p");
      status.id = "storage-warning";
      status.setAttribute("role", "status");
      document.querySelector(".md-content__inner")?.prepend(status);
    }
    status.textContent = message;
  }
  try {
    const saved = localStorage.getItem(KEY);
    if (saved) state = clean(JSON.parse(saved));
  } catch (_) {
    notify("无法读取本地进度。当前操作仍可使用，但进度可能无法保存；请检查浏览器存储设置。");
  }
  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
      return true;
    } catch (_) {
      notify("进度未能保存到浏览器。请导出备份，并检查浏览器存储空间或权限。");
      return false;
    }
  }
  const catalogPromise = fetch(new URL("catalog.json", scriptUrl)).then(response => {
    if (!response.ok) throw new Error("目录加载失败");
    return response.json();
  });
  const controls = document.querySelector("[data-lesson-id]");
  const id = controls?.dataset.lessonId;
  const toggle = document.getElementById("toggle-completed");
  function renderToggle() {
    if (!toggle) return;
    const completed = !!state.lessons[id]?.completed;
    toggle.textContent = completed ? "标记未完成" : "标记已完成";
    toggle.setAttribute("aria-pressed", String(completed));
    controls.classList.toggle("is-completed", completed);
  }
  let readyToSaveScroll = false;
  if (id) {
    state.lessons[id] ||= { completed: false, scroll: 0 };
    const restoreY = state.lessons[id].scroll;
    state.lastRead = { id };
    save();
    renderToggle();
    toggle?.addEventListener("click", () => {
      state.lessons[id].completed = !state.lessons[id].completed;
      const success = save();
      renderToggle();
      document.getElementById("save-status").textContent = success ? "已保存在当前浏览器" : "保存失败，请导出备份";
    });
    async function restore() {
      try { await window.MathJax?.startup?.promise; } catch (_) { /* text remains readable */ }
      if (!location.hash && restoreY > 0) window.scrollTo(0, restoreY);
      requestAnimationFrame(() => { readyToSaveScroll = true; });
    }
    if (document.readyState === "complete") restore();
    else window.addEventListener("load", restore, { once: true });
    function saveScroll() {
      if (!readyToSaveScroll) return;
      state.lessons[id].scroll = Math.round(window.scrollY);
      save();
    }
    let timer;
    window.addEventListener("scroll", () => {
      clearTimeout(timer);
      timer = setTimeout(saveScroll, 250);
    }, { passive: true });
    window.addEventListener("pagehide", saveScroll);
    document.addEventListener("visibilitychange", () => { if (document.hidden) saveScroll(); });
  }
  async function renderDashboard() {
    if (!document.getElementById("learning-dashboard")) return;
    const catalog = await catalogPromise;
    const lessons = catalog.lessons;
    const completed = lessons.filter(item => state.lessons[item.id]?.completed).length;
    const percent = lessons.length ? Math.round(completed / lessons.length * 100) : 0;
    document.getElementById("total-count").textContent = lessons.length;
    document.getElementById("completed-count").textContent = completed;
    document.getElementById("progress-percent").textContent = percent + "%";
    document.getElementById("overall-progress").value = percent;
    const recent = lessons.find(item => item.id === state.lastRead?.id);
    const next = recent || lessons.find(item => !state.lessons[item.id]?.completed) || lessons[0];
    const continueLink = document.getElementById("continue-reading");
    if (next) {
      continueLink.href = new URL(next.url, siteBase).href;
      continueLink.textContent = (recent ? "继续阅读：" : "开始阅读：") + next.title + " →";
    }
    document.getElementById("reading-status").textContent = lessons.length ? `共收录 ${lessons.length} 篇文章，已完成 ${completed} 篇。` : "历史正文尚未导入。19 个已知概念已列入学习路径，等待补录。";
    const cards = document.getElementById("stage-cards");
    cards.replaceChildren();
    catalog.stages.forEach((stage, index) => {
      const stageLessons = lessons.filter(item => item.category === stage.id);
      const done = stageLessons.filter(item => state.lessons[item.id]?.completed).length;
      const card = document.createElement("article");
      card.className = "stage-card";
      const tag = document.createElement("span"); tag.className = "stage-number"; tag.textContent = "阶段 " + String(index + 1).padStart(2, "0");
      const heading = document.createElement("h3"); heading.textContent = stage.title;
      const description = document.createElement("p"); description.textContent = stage.description;
      const status = document.createElement("small"); status.textContent = `${done} / ${stageLessons.length} 篇已完成 · ${stage.concepts.length} 个计划概念`;
      const link = document.createElement("a"); link.href = new URL("generated/path/", siteBase).href; link.textContent = "进入学习路径 →";
      card.append(tag, heading, description, status, link);
      cards.append(card);
    });
  }
  renderDashboard().catch(() => notify("文章目录暂时无法加载，请刷新后重试。"));
  document.getElementById("export-progress")?.addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(state, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = "ai-fable-reading-progress.json"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.getElementById("import-progress")?.addEventListener("change", async event => {
    const status = document.getElementById("progress-tool-status");
    const file = event.target.files[0];
    if (!file) return;
    try {
      if (file.size > 2000000) throw new Error("文件过大");
      const imported = clean(JSON.parse(await file.text()));
      state.lessons = { ...state.lessons, ...imported.lessons };
      state.lastRead = imported.lastRead || state.lastRead;
      status.textContent = save() ? "已合并进度，并保存在当前浏览器。" : "已合并，但保存失败，请导出备份。";
      renderToggle();
      await renderDashboard();
    } catch (_) { status.textContent = "导入失败，请选择有效的阅读进度 JSON 文件。"; }
    event.target.value = "";
  });
  window.addEventListener("storage", event => {
    if (event.key !== KEY) return;
    try {
      state = event.newValue ? clean(JSON.parse(event.newValue)) : empty();
      if (id) state.lessons[id] ||= { completed: false, scroll: 0 };
      renderToggle();
      renderDashboard().catch(() => {});
    } catch (_) { notify("另一个标签页的进度格式无效，请导出备份后检查。"); }
  });
})();
