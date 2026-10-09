"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { recommendation } = require("../docs/assets/progress.js");
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

test("存在概率统计文章：首次推荐仍为主线，支线阅读独立接续", () => {
  assert.ok(navigation["probability-statistics"].some(item => item.published));
  let result = recommendation(navigation, state());
  assert.equal(result.item.id, "vectors-and-matrices");
  assert.equal(result.track, "main");
  const unfinished = state([], "conditional-probability");
  result = recommendation(navigation, unfinished);
  assert.equal(result.kind, "resume");
  assert.equal(result.item.id, "conditional-probability");
  result = recommendation(navigation, state(["conditional-probability"], "conditional-probability"));
  assert.equal(result.item.id, "bayes-theorem");
  assert.equal(result.track, "probability-statistics");
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
