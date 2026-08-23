"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const templatePath = path.join(__dirname, "..", "website", "templates", "flip_cards.html");
const template = fs.readFileSync(templatePath, "utf8");
const start = template.indexOf("    function recordMatches(record) {");
const end = template.indexOf("    function filterTrackPayload(action) {");
assert.ok(start >= 0 && end > start, "progressive render helper block should exist");

const records = Array.from({ length: 120 }, (_, index) => ({
  question_id: `q-${index}`,
  qtime: index,
  member_key: "jiayi",
  status: "answered",
  answer_type: index % 3 === 0 ? "audio" : "text"
}));
const chatScroll = {
  scrollTop: 0,
  style: { scrollBehavior: "smooth" }
};
const context = {
  records,
  memberFilter: { value: "all" },
  statusFilter: { value: "all" },
  typeFilter: { value: "all" },
  renderedRecordLimit: 50,
  loadingOlderRecords: true,
  INITIAL_RENDER_RECORDS: 50,
  chatScroll,
  recordMemberKey: record => record.member_key
};
vm.createContext(context);
vm.runInContext(
  template.slice(start, end) + `
    this.matchingRecordsChronologically = matchingRecordsChronologically;
    this.recordsForCurrentRender = recordsForCurrentRender;
    this.setChatScrollTopImmediately = setChatScrollTopImmediately;
    this.resetProgressiveRender = resetProgressiveRender;
  `,
  context
);

let rendered = context.recordsForCurrentRender(context.matchingRecordsChronologically());
assert.equal(rendered.length, 50);
assert.equal(rendered[0].question_id, "q-70");
assert.equal(rendered.at(-1).question_id, "q-119");

context.renderedRecordLimit = 100;
rendered = context.recordsForCurrentRender(context.matchingRecordsChronologically());
assert.equal(rendered.length, 100);
assert.equal(rendered[0].question_id, "q-20");

context.setChatScrollTopImmediately(4321);
assert.equal(chatScroll.scrollTop, 4321);
assert.equal(chatScroll.style.scrollBehavior, "smooth");

context.resetProgressiveRender();
assert.equal(context.renderedRecordLimit, 50);
assert.equal(context.loadingOlderRecords, false);

assert.match(template, /audio\.preload = "none"/);
assert.doesNotMatch(template, /audio\.preload = "metadata"/);
console.log("flip cards progressive render checks passed");
