(() => {
  "use strict";
  function recommendation(navigation, state) {
    const completed = item => !!state.lessons[item.id]?.completed;
    const all = Object.values(navigation).flat();
    const recent = all.find(item => item.id === state.lastRead?.id && item.published);
    const track = recent ? Object.keys(navigation).find(key => navigation[key].includes(recent)) : "main";
    const courses = navigation[track] || [];
    if (recent && !completed(recent)) return { item: recent, kind: "resume", track };
    const remaining = courses.filter(item => !completed(item));
    if (!remaining.length) return { item: recent || courses[0], kind: "complete", track };
    const recentIndex = recent ? courses.indexOf(recent) : -1;
    const candidate = courses.slice(recentIndex + 1).find(item => !completed(item)) || remaining[0];
    const byId = new Map(all.map(item => [item.id, item]));
    function resolve(item, visited = new Set()) {
      if (!item.published) return { item, kind: "pending", track };
      if (visited.has(item.id)) return { item, kind: "blocked", track };
      const path = new Set(visited).add(item.id);
      const prerequisites = item.prerequisites.filter(id => !state.lessons[id]?.completed).map(id => {
        const prerequisite = byId.get(id);
        return prerequisite ? resolve(prerequisite, path) : { item, kind: "blocked", track };
      });
      // A missing required body takes precedence; never substitute an unrelated course.
      return prerequisites.find(result => result.kind === "pending" || result.kind === "blocked")
        || prerequisites[0] || { item, kind: "next", track };
    }
    return resolve(candidate);
  }
  // Exercise the same production recommendation function without a browser or storage writes.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { recommendation };
    return;
  }
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
  }).catch(() => null);
  const controls = document.querySelector("[data-lesson-id]");
  const id = controls?.dataset.lessonId;
  const toggle = document.getElementById("toggle-completed");
  function renderToggle() {
    if (!toggle) return;
    const completed = !!state.lessons[id]?.completed;
    toggle.textContent = completed ? "标记未完成" : "标记已完成";
    toggle.setAttribute("aria-pressed", String(completed));
    controls.classList.toggle("is-completed", completed);
    document.getElementById("reading-label").textContent = completed ? "已完成" : "未完成";
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
  const isCompleted = item => !!state.lessons[item.id]?.completed;
  const readingState = courseId => state.lessons[courseId]?.completed ? "completed"
    : state.lessons[courseId] || state.lastRead?.id === courseId ? "reading" : "unread";
  function renderCourseStates() {
    document.querySelectorAll("[data-course-id], [data-library-id]").forEach(row => {
      const courseId = row.dataset.courseId || row.dataset.libraryId;
      const completed = !!state.lessons[courseId]?.completed;
      const opened = !!state.lessons[courseId] || state.lastRead?.id === courseId;
      const status = row.querySelector("[data-course-status], [data-library-status]");
      if (status) {
        status.hidden = false;
        status.textContent = completed ? "已完成" : opened ? "阅读中" : row.dataset.courseId ? "已发布 · 未学习" : "未读";
      }
      row.dataset.readingState = readingState(courseId);
    });
    renderLibrary();
  }
  const library = document.getElementById("article-library");
  const libraryRows = library ? [...library.querySelectorAll("[data-library-id]")] : [];
  const query = document.getElementById("library-query");
  const domain = document.getElementById("library-domain");
  const statusFilter = document.getElementById("library-state");
  const sort = document.getElementById("library-sort");
  const normalize = value => value.normalize("NFKC").toLocaleLowerCase().trim();
  function renderLibrary() {
    if (!library) return;
    const terms = normalize(query.value).split(/\s+/).filter(Boolean);
    let visible = 0;
    for (const row of libraryRows) {
      const status = readingState(row.dataset.libraryId);
      const match = (!domain.value || row.dataset.domain === domain.value)
        && (!statusFilter.value || (statusFilter.value === "unfinished" ? status !== "completed" : status === statusFilter.value))
        && terms.every(term => normalize(row.dataset.search).includes(term));
      row.hidden = !match;
      if (match) visible++;
      row.querySelectorAll(".library-date").forEach(date => { date.hidden = sort.value !== "recent"; });
    }
    const rank = row => Number(row.dataset.rank);
    const timestamp = row => Date.parse(row.dataset.added) || 0;
    const ordered = [...libraryRows].sort((a, b) => (sort.value === "recent" ? timestamp(b) - timestamp(a) : 0) || rank(a) - rank(b));
    // Move existing native links; filtering never rewrites article URLs or progress.
    const list = library.querySelector(".library-list");
    ordered.forEach(row => list.append(row));
    document.getElementById("library-count").textContent = `${visible} 篇符合条件 · 共 ${libraryRows.length} 篇已发布`;
    document.getElementById("library-empty").hidden = visible !== 0;
    document.getElementById("library-date-note").hidden = sort.value !== "recent";
  }
  if (library) {
    const params = new URLSearchParams(location.search);
    if ([...domain.options].some(option => option.value === params.get("domain"))) domain.value = params.get("domain");
    if (params.get("sort") === "recent") sort.value = "recent";
    library.querySelector("form").addEventListener("submit", event => event.preventDefault());
    query.addEventListener("input", renderLibrary);
    [domain, statusFilter, sort].forEach(control => control.addEventListener("change", renderLibrary));
    library.querySelector(".library-filters").hidden = false;
  }
  function catalogUnavailable() {
    const status = document.getElementById("reading-status");
    if (status) {
      status.textContent = "暂时无法更新个人推荐；仍可使用上方阅读入口、阶段路线与文章库。刷新可重试。";
      status.setAttribute("role", "status");
    }
  }
  async function renderDashboard() {
    renderCourseStates();
    if (!document.getElementById("learning-dashboard") && !document.querySelector("[data-stage-id]")) return;
    const catalog = await catalogPromise;
    if (!catalog || !Array.isArray(catalog.lessons) || !Array.isArray(catalog.stages) || !Array.isArray(catalog.navigation?.main)) {
      catalogUnavailable();
      return;
    }
    const lessons = catalog.lessons;
    document.querySelectorAll("[data-stage-id]").forEach(card => {
      const stageLessons = lessons.filter(item => item.category === card.dataset.stageId);
      if (!stageLessons.length) return;
      const done = stageLessons.filter(isCompleted).length;
      card.querySelector("[data-stage-status]").textContent = `已发布 ${stageLessons.length} 篇 · ${done === stageLessons.length ? "已完成" : done ? `${done} 篇已完成` : "未学习"}`;
      const progress = card.querySelector("[data-stage-progress]");
      progress.max = stageLessons.length;
      progress.value = done;
    });
    if (!document.getElementById("learning-dashboard")) return;
    const completed = lessons.filter(isCompleted).length;
    const percent = lessons.length ? Math.round(completed / lessons.length * 100) : 0;
    document.getElementById("total-count").textContent = lessons.length;
    document.getElementById("completed-count").textContent = completed;
    document.getElementById("progress-percent").textContent = percent + "%";
    document.getElementById("overall-progress").value = percent;
    document.getElementById("reading-status").textContent = completed ? `已连起 ${completed} 篇知识，按自己的节奏继续。` : "每完成一篇，知识就连起一小段。";
    const { item, kind, track } = recommendation(catalog.navigation, state);
    const continueLink = document.getElementById("continue-reading");
    if (!item) {
      document.getElementById("continue-title").textContent = "教材正在生长";
      document.getElementById("continue-story").textContent = "暂没有已发布正文，可以先了解阶段计划。";
      continueLink.href = new URL("generated/path/", siteBase).href;
      continueLink.textContent = "查看学习路线 →";
      return;
    }
    const stage = catalog.stages.find(stage => stage.id === item.category);
    const concepts = new Map(catalog.stages.flatMap(stage => stage.concepts.map(concept => [concept.id, { ...concept, stage: stage.id }])));
    const title = concepts.get(item.id)?.title || item.title;
    const reason = document.getElementById("continue-reason");
    const trackLabel = track === "main" ? "主线" : "概率与统计支线";
    reason.textContent = kind === "resume" ? "回到上次未读完的课程" : kind === "pending" ? `${trackLabel}课程待发布` : kind === "blocked" ? "等待必要的前置知识" : kind === "complete" ? `${trackLabel}课程已完成，随时回顾` : completed ? `沿着${trackLabel}，继续下一课` : "从主线起点开始";
    const stageLink = document.getElementById("continue-stage");
    stageLink.textContent = stage?.title || "学习路线";
    stageLink.href = new URL(`generated/stages/${item.category}/`, siteBase).href;
    document.getElementById("continue-title").textContent = kind === "blocked" ? "先补齐必要的前置知识" : title + (kind === "pending" ? "（待发布）" : "");
    document.getElementById("continue-story").textContent = kind === "blocked" ? "课程所需的前置知识暂不可用，可在学习路线查看计划。" : kind === "pending" ? "这篇课程正文尚未发布，先在阶段计划查看学习位置与前置知识。" : item.story;
    continueLink.href = new URL(kind === "blocked" ? "generated/path/#prerequisite-gaps" : item.url, siteBase).href;
    continueLink.textContent = kind === "resume" ? "继续阅读 →" : kind === "pending" ? "查看待发布课程 →" : kind === "blocked" ? "查看学习路线 →" : kind === "complete" ? "回顾这一篇 →" : completed ? "阅读下一课 →" : "开始阅读 →";
    const prerequisites = document.getElementById("continue-prerequisites");
    prerequisites.replaceChildren(document.createTextNode("前置知识："));
    if (!item.prerequisites.length) prerequisites.append(document.createTextNode("无需前置，从这里开始。"));
    item.prerequisites.forEach((id, index) => {
      if (index) prerequisites.append(document.createTextNode("、"));
      const prerequisite = lessons.find(lesson => lesson.id === id);
      const concept = concepts.get(id);
      const link = document.createElement("a");
      link.textContent = (concept?.title || prerequisite?.title || id) + (prerequisite ? isCompleted(prerequisite) ? "（已完成）" : "" : "（待发布）");
      link.href = new URL(prerequisite ? prerequisite.url : `generated/stages/${concept?.stage || item.category}/#concept-${id}`, siteBase).href;
      prerequisites.append(link);
    });
  }
  renderDashboard().catch(catalogUnavailable);
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
  window.addEventListener("pageshow", event => {
    if (!event.persisted) return;
    try {
      const saved = localStorage.getItem(KEY);
      state = saved ? clean(JSON.parse(saved)) : empty();
      if (id) {
        state.lessons[id] ||= { completed: false, scroll: 0 };
        state.lastRead = { id };
        save();
      }
      renderToggle();
      renderDashboard().catch(catalogUnavailable);
    } catch (_) { notify("无法更新本地进度，请检查浏览器存储设置。"); }
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
