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

const rows = [
  {
    order_id: "o1",
    item_id: "I1",
    status_kind: "awaiting_shipment",
    broadcast_at: "",
    buyer_id: "2068326847",
    buyer_phone_masked: "177****4879",
    display_name: "徐某人",
    receiver_name: "徐某人",
    buyer_note: "",
    seller_note: "",
    item_name: "百场应援",
    sku_title: "1005"
  },
  {
    order_id: "o2",
    item_id: "I1",
    status_kind: "shipped",
    broadcast_at: "2026-11-01 10:00:00",
    buyer_id: "2111166808",
    buyer_phone_masked: "852****0725",
    display_name: "ama",
    receiver_name: "ama",
    buyer_note: "",
    seller_note: "",
    item_name: "补邮",
    sku_title: ""
  },
  {
    order_id: "o3",
    item_id: "I2",
    status_kind: "awaiting_shipment",
    broadcast_at: "",
    buyer_id: "9999999999",
    buyer_phone_masked: "138****0000",
    display_name: "真实买家",
    receiver_name: "真实买家",
    buyer_note: "",
    seller_note: "",
    item_name: "百场应援",
    sku_title: "52"
  },
  {
    order_id: "o4",
    item_id: "I2",
    status_kind: "awaiting_shipment",
    broadcast_at: "",
    buyer_id: "",
    buyer_phone_masked: "",
    display_name: "旧订单",
    receiver_name: "旧订单",
    buyer_note: "",
    seller_note: "",
    item_name: "百场应援",
    sku_title: ""
  }
];

function match(overrides) {
  return rows
    .filter(row =>
      context.orderMatchesFilters(
        row,
        Object.assign({ status: "all", item: "all", keyword: "", accounts: {} }, overrides || {})
      )
    )
    .map(row => row.order_id);
}

assert.deepEqual(match(), ["o1", "o2", "o3", "o4"], "empty account filter keeps all orders");
assert.deepEqual(
  match({ accounts: { "2068326847": true, "2111166808": true } }),
  ["o1", "o2"],
  "multi-select keeps only the selected accounts"
);
assert.deepEqual(match({ accounts: { "2111166808": true } }), ["o2"], "single account selection");
assert.deepEqual(match({ accounts: { __unknown__: true } }), ["o4"], "unknown account bucket");
assert.deepEqual(match({ keyword: "2111166808" }), ["o2"], "keyword matches buyer id");
assert.deepEqual(match({ keyword: "177****4879" }), ["o1"], "keyword matches masked phone");
assert.deepEqual(match({ keyword: "补邮" }), ["o2"], "keyword still matches item name");
assert.deepEqual(match({ status: "awaiting_shipment" }), ["o1", "o3", "o4"], "status filter still works");
assert.deepEqual(match({ item: "I2" }), ["o3", "o4"], "item filter still works");
assert.deepEqual(match({ status: "broadcast_none", accounts: { "2111166808": true } }), [], "broadcast filter combines with account");

assert.equal(context.accountKey({ buyer_id: "2068326847" }), "2068326847");
assert.equal(context.accountKey({ buyer_id: "" }), "__unknown__");
assert.equal(context.accountLabel({ buyer_id: "2068326847", buyer_phone_masked: "177****4879" }), "177****4879 · ID 2068326847");
assert.equal(context.accountLabel({ buyer_id: "", buyer_phone_masked: "" }), "未知账号");

console.log("weidian orders frontend account filter tests passed");
