"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const templatePath = path.join(__dirname, "..", "website", "templates", "weidian_orders.html");
const template = fs.readFileSync(templatePath, "utf8");
const startMarker = "// WEIDIAN_ACCOUNT_FILTER_PURE_START";
const endMarker = "// WEIDIAN_ACCOUNT_FILTER_PURE_END";
const start = template.indexOf(startMarker);
const end = template.indexOf(endMarker);
assert.ok(start >= 0 && end > start, "account filter pure helper block should exist");

const context = {};
vm.createContext(context);
vm.runInContext(
  template.slice(start + startMarker.length, end) + `
    this.accountKey = accountKey;
    this.accountLabel = accountLabel;
    this.orderMatchesFilters = orderMatchesFilters;
  `,
  context
);

function row(overrides) {
  return Object.assign(
    {
      order_id: "",
      item_id: "I1",
      status_kind: "awaiting_shipment",
      broadcast_at: "",
      buyer_id: "",
      buyer_phone_masked: "",
      display_name: "",
      receiver_name: "",
      buyer_note: "",
      seller_note: "",
      item_name: "百场应援",
      sku_title: ""
    },
    overrides
  );
}

const rows = [
  row({ order_id: "o1", buyer_id: "2068326847", buyer_phone_masked: "177****4879", display_name: "徐某人", receiver_name: "徐某人" }),
  row({ order_id: "o2", item_name: "补邮", status_kind: "shipped", buyer_id: "2111166808", buyer_phone_masked: "852****0725", display_name: "ama", receiver_name: "ama" }),
  row({ order_id: "o3", item_id: "I2", buyer_id: "9999999999", buyer_phone_masked: "138****0000", display_name: "真实买家", receiver_name: "真实买家" }),
  row({ order_id: "o4", item_id: "I2", display_name: "旧订单", receiver_name: "旧订单" }),
  row({ order_id: "o5", status_kind: "closed", buyer_id: "9999999999", buyer_phone_masked: "138****0000", display_name: "已关闭", receiver_name: "已关闭" }),
  row({ order_id: "o6", status_kind: "refunded", buyer_id: "2111166808", buyer_phone_masked: "852****0725", display_name: "已退款", receiver_name: "已退款" }),
  row({ order_id: "o7", status_kind: "completed", buyer_id: "9999999999", buyer_phone_masked: "138****0000", display_name: "已完成", receiver_name: "已完成" })
];

function match(overrides) {
  return rows
    .filter(item =>
      context.orderMatchesFilters(
        item,
        Object.assign({ status: "all", item: "all", keyword: "", accounts: {} }, overrides || {})
      )
    )
    .map(item => item.order_id);
}

assert.deepEqual(match(), ["o1", "o2", "o3", "o4", "o5", "o6", "o7"], "empty filters keep all orders");
assert.deepEqual(
  match({ accounts: { "2068326847": true, "2111166808": true } }),
  ["o1", "o2", "o6"],
  "multi-select keeps only the selected accounts"
);
assert.deepEqual(match({ accounts: { "2111166808": true } }), ["o2", "o6"], "single account selection");
assert.deepEqual(match({ accounts: { __unknown__: true } }), ["o4"], "unknown account bucket");
assert.deepEqual(match({ keyword: "2111166808" }), ["o2", "o6"], "keyword matches buyer id");
assert.deepEqual(match({ keyword: "177****4879" }), ["o1"], "keyword matches masked phone");
assert.deepEqual(match({ keyword: "补邮" }), ["o2"], "keyword still matches item name");
assert.deepEqual(match({ status: "awaiting_shipment" }), ["o1", "o3", "o4"], "awaiting filter");
assert.deepEqual(match({ status: "closed" }), ["o5"], "closed filter is separate");
assert.deepEqual(match({ status: "refunded" }), ["o6"], "refunded filter is separate");
assert.deepEqual(match({ status: "completed" }), ["o7"], "completed filter");
assert.deepEqual(match({ item: "I2" }), ["o3", "o4"], "item filter still works");
assert.deepEqual(match({ item: "I2", accounts: { __unknown__: true } }), ["o4"], "filters combine");

assert.equal(context.accountKey({ buyer_id: "2068326847" }), "2068326847");
assert.equal(context.accountKey({ buyer_id: "" }), "__unknown__");
assert.equal(context.accountLabel({ buyer_id: "2068326847", buyer_phone_masked: "177****4879" }), "177****4879 · ID 2068326847");
assert.equal(context.accountLabel({ buyer_id: "", buyer_phone_masked: "" }), "未知账号");

console.log("weidian orders frontend account filter tests passed");
