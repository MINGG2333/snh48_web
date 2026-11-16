"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const templatePath = path.join(__dirname, "..", "website", "templates", "replay.html");
const template = fs.readFileSync(templatePath, "utf8");

const scriptBlocks = Array.from(template.matchAll(/<script>([\s\S]*?)<\/script>/g)).map(match => match[1]);
const inlineScript = scriptBlocks.find(block => block.includes("DOMContentLoaded"));
assert.ok(inlineScript, "replay.html should keep its inline player script");

// 把 Jinja 表达式替换成 null 后再做语法检查，避免测试依赖服务端渲染上下文。
const parseableScript = inlineScript.replace(/\{\{[\s\S]*?\}\}/g, "null");
assert.doesNotThrow(() => new Function(parseableScript), "replay inline script should parse");

assert.match(inlineScript, /let playIntent = false;/, "player should track user playback intent");
assert.match(
  inlineScript,
  /document\.addEventListener\(['"]visibilitychange['"]/,
  "player should react to page visibility changes"
);
assert.match(
  inlineScript,
  /function attemptBackgroundResume\(\)/,
  "player should resume the same video element when backgrounded"
);
assert.match(
  inlineScript,
  /if \(!document\.hidden \|\| !playIntent \|\| backgroundAudioBlocked \|\| !video\.paused \|\| video\.ended\) return;/,
  "background resume should only run while hidden, intended, and paused"
);
assert.match(
  inlineScript,
  /navigator\.audioSession\.type = 'playback'/,
  "player should request a playback audio session where supported"
);
assert.match(
  inlineScript,
  /url\.includes\('\.m3u8'\) && !isIOSDevice && typeof Hls !== 'undefined' && Hls\.isSupported\(\)/,
  "iOS should use native HLS instead of an MSE pipeline that stalls when background JS is suspended"
);
assert.match(
  inlineScript,
  /navigator\.mediaSession\.setActionHandler\(action/,
  "player should expose media session actions for lock-screen controls"
);
assert.match(
  inlineScript,
  /pause: \(\) => \{\s*playIntent = false;/,
  "media session pause should clear playback intent so auto-resume does not fight the user"
);
assert.match(
  inlineScript,
  /current > lastDanmuSyncTime \+ 3/,
  "danmu should resync instead of flushing missed items after a large forward jump"
);
assert.match(
  inlineScript,
  /if \(document\.hidden\) \{\s*lastDanmuSyncTime = current;\s*return;/,
  "danmu rendering should pause while the page is hidden"
);

console.log("replay background playback contract: ok");
