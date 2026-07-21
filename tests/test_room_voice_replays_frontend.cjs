"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeElement {
  constructor(tagName, id = "") {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.hidden = false;
    this.className = "";
    this.textContent = "";
    this.children = [];
    this.dataset = {};
    this.listeners = new Map();
    this.attributes = new Map();
    this.parentNode = null;
    this.value = "";
    this.paused = true;
    this.ended = false;
    this.currentTime = 0;
    this.duration = 120;
    this.readyState = 0;
    this.seeking = false;
    this.classList = {
      add: name => {
        const names = new Set(this.className.split(/\s+/).filter(Boolean));
        names.add(name);
        this.className = Array.from(names).join(" ");
      },
      remove: name => {
        this.className = this.className.split(/\s+/).filter(item => item && item !== name).join(" ");
      }
    };
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  replaceChildren(...children) {
    this.children = [];
    children.forEach(child => this.appendChild(child));
  }

  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }

  removeEventListener(name, callback) {
    this.listeners.set(name, (this.listeners.get(name) || []).filter(item => item !== callback));
  }

  dispatch(name, event = {}) {
    for (const callback of [...(this.listeners.get(name) || [])]) callback(event);
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  contains(node) {
    for (let current = node; current; current = current.parentNode) {
      if (current === this) return true;
    }
    return false;
  }

  closest() {
    return null;
  }

  querySelector(selector) {
    const indexMatch = selector.match(/^\[data-index="(\d+)"\]$/);
    if (!indexMatch) return null;
    return this.children.find(child => child.dataset.index === indexMatch[1]) || null;
  }

  pause() {
    this.paused = true;
  }

  play() {
    this.paused = false;
    return Promise.resolve();
  }

  load() {}
  scrollIntoView() {}
}

const templatePath = path.join(__dirname, "..", "website", "templates", "room_voice_replays.html");
const template = fs.readFileSync(templatePath, "utf8");
const inlineScriptMatch = template.match(/\n  <script>\n([\s\S]*?)\n  <\/script>/);
assert.ok(inlineScriptMatch, "room voice inline script should exist");

const elementIds = [
  "loginWrap", "app", "logoutBtn", "loginForm", "passwordInput", "loginError", "roomFilter",
  "sessionList", "detailEmpty", "detailContent", "audioPlayer", "playbackMode", "playbackModeNote",
  "playbackStatus", "playbackStatusText", "messages", "messageCount", "segmentLabel", "timelineLabel",
  "stats", "participants", "sessionHeading", "roomTag"
];
const elements = Object.fromEntries(elementIds.map(id => [id, new FakeElement("div", id)]));
elements.roomFilter.value = "all";
const timers = new Map();
let nextTimerId = 1;
let selection = { isCollapsed: true, toString: () => "", anchorNode: null, focusNode: null };
const trackedEvents = [];

const context = {
  console,
  HTMLMediaElement: { HAVE_METADATA: 1 },
  _trackEvent: (eventType, data) => trackedEvents.push({ eventType, data }),
  document: {
    getElementById: id => elements[id],
    createElement: tagName => new FakeElement(tagName)
  },
  fetch: async () => ({ ok: true, json: async () => ({ sessions: [] }) }),
  setTimeout: callback => {
    const id = nextTimerId++;
    timers.set(id, callback);
    return id;
  },
  clearTimeout: id => timers.delete(id),
  getSelection: () => selection
};
context.window = context;
vm.createContext(context);
vm.runInContext(inlineScriptMatch[1], context);

vm.runInContext(`
  currentSession = {
    wall_duration_seconds: 120,
    segments: [{
      segment_no: 1,
      wall_start_offset_seconds: 10,
      variants: { compatible: { media_url: "/audio/segment_000001.m4a" } }
    }]
  };
  currentSessionId = "session-test";
  currentSegmentIndex = 0;
  currentMessages = [
    { audio_covered: true, segment_no: 1, offset_ms: 30000, sender_name: "成员", text_content: "可跳转消息" },
    { audio_covered: false, segment_no: null, offset_ms: 40000, sender_name: "成员", text_content: "缺口消息" }
  ];
  renderMessages();
`, context);

const [playableRow, gapRow] = elements.messages.children;
assert.match(playableRow.className, /\bseekable\b/);
assert.equal(playableRow.getAttribute("role"), "button");
assert.equal(playableRow.tabIndex, 0);
assert.equal(playableRow.children[0].tagName, "SPAN");
assert.ok(playableRow.listeners.has("click"));
assert.ok(playableRow.listeners.has("keydown"));
assert.match(gapRow.className, /\bgap\b/);
assert.equal(gapRow.listeners.has("click"), false);

const audio = elements.audioPlayer;
audio.readyState = 1;
audio.setAttribute("src", "/audio/segment_000001.m4a");
audio.currentTime = 2;
selection = {
  isCollapsed: false,
  toString: () => "可跳转消息",
  anchorNode: playableRow.children[1],
  focusNode: playableRow.children[1]
};
playableRow.dispatch("click", { target: playableRow });
assert.equal(audio.currentTime, 2, "selecting message text must not seek audio");

selection = { isCollapsed: true, toString: () => "", anchorNode: null, focusNode: null };
playableRow.dispatch("click", { target: playableRow });
assert.equal(audio.currentTime, 20, "clicking a covered message should seek within the segment");
assert.equal(elements.playbackStatus.hidden, false);
assert.equal(elements.playbackStatusText.textContent, "正在跳转到 00:30…");
audio.dispatch("seeked");
assert.equal(elements.playbackStatus.hidden, true);

audio.currentTime = 4;
let prevented = false;
playableRow.dispatch("keydown", {
  target: playableRow,
  key: " ",
  preventDefault: () => { prevented = true; }
});
assert.equal(prevented, true);
assert.equal(audio.currentTime, 20, "Space should activate a covered message row");
audio.dispatch("seeked");

audio.currentTime = 40;
audio.seeking = true;
audio.dispatch("seeking");
assert.equal(elements.playbackStatusText.textContent, "正在跳转到 00:50…");
assert.equal(timers.size, 1);
Array.from(timers.values())[0]();
assert.equal(elements.playbackStatusText.textContent, "跳转加载时间较长，请继续等待…");
audio.seeking = false;
audio.dispatch("seeked");
assert.equal(elements.playbackStatus.hidden, true);

audio.dispatch("waiting");
assert.equal(elements.playbackStatusText.textContent, "正在加载音频…");
audio.dispatch("canplay");
assert.equal(elements.playbackStatus.hidden, true);
audio.dispatch("error");
assert.match(elements.playbackStatus.className, /\berror\b/);
assert.equal(elements.playbackStatusText.textContent, "音频加载失败，请重试或切换播放模式。");

audio.ended = false;
audio.paused = false;
audio.dispatch("play");
audio.paused = true;
audio.dispatch("pause");
audio.ended = true;
audio.dispatch("ended");

const trackedActions = trackedEvents.map(event => event.data.action);
for (const action of [
  "room_voice_message_seek",
  "room_voice_seek",
  "room_voice_play",
  "room_voice_pause",
  "room_voice_segment_complete"
]) {
  assert.ok(trackedActions.includes(action), `expected tracked action: ${action}`);
}
assert.equal(
  trackedEvents.some(event => event.data._push_to_notification),
  false,
  "room voice interaction events must not request notifications"
);

vm.runInContext("hidePlaybackStatus()", context);
console.log("room voice frontend interaction checks passed");
