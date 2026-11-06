"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { recommendation, clean, mergeProgress, courseReadingState, validTrack } = require("../docs/assets/progress.js");
const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const navigation = payload.navigation || payload;
const state = (ids = [], lastRead = null) => ({
  version: 1,
  lessons: Object.fromEntries(ids.map(id => [id, { completed: true, scroll: 321 }])),
  lastRead: lastRead ? { id: lastRead } : null,
});
const trainingEnd = "partial-derivative-and-gradient";
const throughTraining = navigation.main.slice(0, navigation.main.findIndex(item => item.id === trainingEnd) + 1).map(item => item.id);

test("训练课程新增后，推荐能由待发布自动转为已发布，不跳 CNN 或统计支线", () => {
  const progress = state(throughTraining, trainingEnd);
  const before = JSON.stringify(progress);
  const result = recommendation(navigation, progress);
  const nextCourse = navigation.main.find((item, index) =>
    index === navigation.main.findIndex(course => course.id === trainingEnd) + 1);
  assert.ok(nextCourse);
  assert.equal(result.kind, nextCourse.published ? "next" : "pending");
  assert.equal(result.item.id, nextCourse.id);
  assert.equal(result.item.url, nextCourse.url);
  assert.equal(result.track, "main");
  assert.equal(JSON.stringify(progress), before, "推荐不得改写进度");
});

test("下一篇或必要前置未发布：显示待发布，不越过缺口", () => {
  const fixture = structuredClone(navigation);
  fixture.main.find(item => item.id === "matrix-multiplication").published = false;
  fixture.main.find(item => item.id === "matrix-multiplication").url = "generated/stages/foundations/#concept-matrix-multiplication";
  let result = recommendation(fixture, state(["vectors-and-matrices"], "vectors-and-matrices"));
  assert.equal(result.kind, "pending");
  assert.equal(result.item.id, "matrix-multiplication");
  // A later published course also stops at its missing prerequisite.
  result = recommendation(fixture, state(["vectors-and-matrices", "tensor-shape"], "tensor-shape"));
  assert.equal(result.kind, "pending");
  assert.equal(result.item.id, "matrix-multiplication");
});

test("存在概率统计文章：首次推荐仍为主线，主动选择参考路线后独立接续", () => {
  assert.ok(navigation["probability-statistics"].some(item => item.published));
  let result = recommendation(navigation, state());
  assert.equal(result.item.id, "vectors-and-matrices");
  assert.equal(result.track, "main");
  const unfinished = state([], "conditional-probability");
  result = recommendation(navigation, unfinished);
  assert.equal(result.track, "main");
  assert.equal(result.item.id, "vectors-and-matrices");
  result = recommendation(navigation, unfinished, "probability-statistics");
  assert.equal(result.kind, "resume");
  assert.equal(result.item.id, "conditional-probability");
  result = recommendation(navigation, state(["conditional-probability"], "conditional-probability"), "probability-statistics");
  assert.equal(result.item.id, "bayes-theorem");
  assert.equal(result.track, "probability-statistics");
});

test("进阶规划、发布、阅读与完成状态遵循真实正文", () => {
  const fixture = structuredClone(navigation);
  fixture.applied.forEach(item => {
    item.published = false;
    item.url = `generated/stages/${item.category}/#concept-${item.id}`;
  });
  const first = fixture.applied[0];
  const progress = state(fixture.main.map(item => item.id), fixture.main.at(-1).id);
  let result = recommendation(fixture, progress, "applied");
  assert.equal(result.track, "applied");
  assert.equal(result.kind, "pending");
  assert.equal(result.item.id, "problem-framing-and-baseline");
  assert.equal(courseReadingState(progress, first), "planned");
  // Even an imported completion entry cannot turn an unpublished concept into a lesson.
  assert.equal(courseReadingState(state([first.id]), first), "planned");
  const premature = state(fixture.applied.map(item => item.id));
  assert.equal(recommendation(fixture, premature, "applied").kind, "pending");
  first.published = true;
  first.url = "lessons/synthetic-problem-framing-and-baseline/";
  result = recommendation(fixture, progress, "applied");
  assert.equal(result.kind, "next");
  assert.equal(result.item.url, first.url);
  assert.equal(courseReadingState(progress, first), "unread");
  progress.lessons[first.id] = { completed: false, scroll: 123 };
  progress.lastRead = { id: first.id };
  assert.equal(courseReadingState(progress, first), "reading");
  assert.equal(recommendation(fixture, progress, "applied").kind, "resume");
  progress.lessons[first.id].completed = true;
  assert.equal(courseReadingState(progress, first), "completed");
  result = recommendation(fixture, progress, "applied");
  assert.equal(result.item.id, "data-quality-and-leakage");
  assert.equal(result.kind, "pending");
});

test("路线由用户选择，跨路线前置知识只提示，不自动跳转", () => {
  const fixture = structuredClone(navigation);
  fixture.applied[0].published = true;
  const result = recommendation(fixture, state(), "applied");
  assert.equal(result.kind, "prerequisites");
  assert.equal(result.track, "applied");
  assert.equal(result.item.id, fixture.applied[0].id);
  const completedMain = state(fixture.main.map(item => item.id), "conditional-probability");
  assert.equal(recommendation(fixture, completedMain).kind, "complete");
  assert.equal(recommendation(fixture, completedMain).track, "main");
  assert.equal(validTrack("applied"), "applied");
  for (const invalid of [null, "ocr", "toString", "__proto__", "unknown"]) assert.equal(validTrack(invalid), "main");
});

test("旧 v1 进度合并与导出往返保留基础、参考和 OCR 状态及滚动位置", () => {
  const legacy = state(["vectors-and-matrices", "conditional-probability", "ocr-pixels-rgb"], "ocr-pixels-rgb");
  legacy.lessons["ocr-convolution-features"] = { completed: false, scroll: 654 };
  const before = JSON.stringify(legacy);
  assert.deepEqual(clean(JSON.parse(before)), legacy);
  const current = state(["problem-framing-and-baseline"]);
  const merged = mergeProgress(current, JSON.parse(before));
  for (const [id, entry] of Object.entries(legacy.lessons)) assert.deepEqual(merged.lessons[id], entry);
  assert.deepEqual(merged.lessons["problem-framing-and-baseline"], current.lessons["problem-framing-and-baseline"]);
  assert.deepEqual(clean(JSON.parse(JSON.stringify(merged))), merged);
  assert.equal(JSON.stringify(legacy), before);
  assert.equal(Object.hasOwn(merged, "selectedTrack"), false);
  assert.throws(() => clean({ version: 2, lessons: {} }));
});

test("OCR 独立目录保持原有接续、缺口与完成行为", () => {
  const courses = [
    { id: "ocr-pixels-rgb", published: true, prerequisites: [], url: "ocr/chapters/undated-ocr-pixels-rgb/" },
    { id: "ocr-convolution-features", published: false, prerequisites: ["ocr-pixels-rgb"], url: "ocr/#ocr-convolution-features" },
  ];
  let result = recommendation({ main: courses }, state());
  assert.equal(result.item.id, courses[0].id);
  assert.equal(result.kind, "next");
  result = recommendation({ main: courses }, state([], courses[0].id));
  assert.equal(result.kind, "resume");
  result = recommendation({ main: courses }, state([courses[0].id], courses[0].id));
  assert.equal(result.kind, "pending");
  assert.equal(result.item.url, courses[1].url);
  courses[1].published = true;
  assert.equal(recommendation({ main: courses }, state(courses.map(c => c.id))).kind, "complete");
});

test("全部主线完成：提供主线回顾，不自动切换未读的概率支线", () => {
  const fixture = structuredClone(navigation);
  fixture.main.forEach(item => { item.published = true; item.url = `lessons/test-${item.id}/`; });
  const progress = state(fixture.main.map(item => item.id), fixture.main.at(-1).id);
  const result = recommendation(fixture, progress);
  assert.equal(result.kind, "complete");
  assert.equal(result.track, "main");
  assert.equal(result.item.id, fixture.main.at(-1).id);
  // Newly published lessons change the first remaining gap; never hardcode its id.
  const publishedDone = recommendation(navigation, state(navigation.main.filter(item => item.published).map(item => item.id)));
  const firstMissing = navigation.main.find(item => !item.published);
  assert.equal(publishedDone.track, "main");
  if (firstMissing) {
    assert.equal(publishedDone.kind, "pending");
    assert.equal(publishedDone.item.id, firstMissing.id);
  } else {
    assert.equal(publishedDone.kind, "complete");
  }
});
