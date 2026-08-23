"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const sourcePath = path.join(__dirname, "..", "website", "static", "js", "timeline.js");
const source = fs.readFileSync(sourcePath, "utf8");
const start = source.indexOf("function secondaryPerformanceBadge(event) {");
const end = source.indexOf("\n// ═", start);
assert.ok(start >= 0 && end > start, "secondary performance badge helper should exist");

const context = {};
vm.createContext(context);
vm.runInContext(
  source.slice(start, end) + "\nthis.secondaryPerformanceBadge = secondaryPerformanceBadge;",
  context
);

assert.equal(
  context.secondaryPerformanceBadge({ type: "里程碑", eventType: "里程碑", title: "陈嘉仪出道首演" }),
  "",
  "milestones should not render a keyword badge"
);
assert.equal(
  context.secondaryPerformanceBadge({ type: "公演", eventType: "行程", title: "《B·RISE 梦之门》新生公演首演" }),
  "milestone|首演",
  "schedule performances should retain the debut badge"
);
assert.equal(
  context.secondaryPerformanceBadge({ type: "公演", eventType: "行程", title: "《赫兹共振》巡演广州站" }),
  "tour|巡演"
);
assert.equal(
  context.secondaryPerformanceBadge({ type: "公演", eventType: "行程", title: "周年公演助演" }),
  "show|助演"
);
assert.equal(
  (source.match(/secondaryPerformanceBadge\(/g) || []).length,
  3,
  "cards and modals should share the badge helper"
);

console.log("timeline badge checks passed");
