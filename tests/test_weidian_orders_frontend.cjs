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
    this.statusMatches = statusMatches;
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
      refund_state: "none",
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
  row({ order_id: "o6", status_kind: "refunded", refund_state: "refunding", buyer_id: "2111166808", buyer_phone_masked: "852****0725", display_name: "退款中", receiver_name: "退款中" }),
  row({ order_id: "o7", status_kind: "completed", buyer_id: "9999999999", buyer_phone_masked: "138****0000", display_name: "已完成", receiver_name: "已完成" }),
  row({ order_id: "o8", status_kind: "refunded", refund_state: "refunded", buyer_id: "9999999999", buyer_phone_masked: "138****0000", display_name: "已退款", receiver_name: "已退款" })
];

function match(overrides) {
  return rows
    .filter(item =>
      context.orderMatchesFilters(
        item,
        Object.assign({ statuses: {}, item: "all", keyword: "", accounts: {} }, overrides || {})
      )
    )
    .map(item => item.order_id);
}

assert.deepEqual(match(), ["o1", "o2", "o3", "o4", "o5", "o6", "o7", "o8"], "empty filters keep all orders");
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
assert.deepEqual(match({ statuses: { awaiting_shipment: true } }), ["o1", "o3", "o4"], "awaiting filter");
assert.deepEqual(match({ statuses: { shipped: true } }), ["o2"], "shipped filter");
assert.deepEqual(match({ statuses: { awaiting_shipment: true, shipped: true } }), ["o1", "o2", "o3", "o4"], "status multi-select union");
assert.deepEqual(match({ statuses: { completed: true } }), ["o7"], "completed filter");
assert.deepEqual(match({ statuses: { closed: true } }), ["o5"], "closed filter");
assert.deepEqual(match({ statuses: { completed: true, closed: true } }), ["o5", "o7"], "finished multi-select union");
assert.deepEqual(match({ statuses: { refunding: true } }), ["o6"], "refunding filter");
assert.deepEqual(match({ statuses: { refunded_only: true } }), ["o8"], "refunded-only filter");
assert.deepEqual(match({ statuses: { refunding: true, refunded_only: true } }), ["o6", "o8"], "refund multi-select union");
assert.deepEqual(match({ item: "I2" }), ["o3", "o4"], "item filter still works");
assert.deepEqual(match({ item: "I2", accounts: { __unknown__: true } }), ["o4"], "filters combine");

assert.equal(context.statusMatches({ status_kind: "refunded", refund_state: "refunding" }, { refunding: true }), true);
assert.equal(context.statusMatches({ status_kind: "refunded", refund_state: "refunding" }, { refunded_only: true }), false);
assert.equal(context.statusMatches({ status_kind: "refunded", refund_state: "refunded" }, { refunded_only: true }), true);
assert.equal(context.statusMatches({ status_kind: "refunded", refund_state: "refunding" }, { refunding: true, refunded_only: true }), true);
assert.equal(context.statusMatches({ status_kind: "closed", refund_state: "none" }, { closed: true }), true);
assert.equal(context.statusMatches({ status_kind: "awaiting_shipment", refund_state: "none" }, {}), true);

assert.equal(context.accountKey({ buyer_id: "2068326847" }), "2068326847");
assert.equal(context.accountKey({ buyer_id: "" }), "__unknown__");
assert.equal(context.accountLabel({ buyer_id: "2068326847", buyer_phone_masked: "177****4879" }), "177****4879 · ID 2068326847");
assert.equal(context.accountLabel({ buyer_id: "", buyer_phone_masked: "" }), "未知账号");

const bulkStartMarker = "// WEIDIAN_BULK_SHIP_PURE_START";
const bulkEndMarker = "// WEIDIAN_BULK_SHIP_PURE_END";
const bulkStart = template.indexOf(bulkStartMarker);
const bulkEnd = template.indexOf(bulkEndMarker);
assert.ok(bulkStart >= 0 && bulkEnd > bulkStart, "bulk ship pure helper block should exist");

const bulkContext = {};
vm.createContext(bulkContext);
vm.runInContext(
  template.slice(bulkStart + bulkStartMarker.length, bulkEnd) + `
    this.isSelectable = isSelectable;
    this.selectableRows = selectableRows;
    this.selectedShipRows = selectedShipRows;
  `,
  bulkContext
);

const bulkRows = [
  row({ order_id: "b1", status_kind: "awaiting_shipment", shipped: false }),
  row({ order_id: "b2", status_kind: "awaiting_shipment", shipped: true }),
  row({ order_id: "b3", status_kind: "shipped", shipped: true }),
  row({ order_id: "b4", status_kind: "refunded", refund_state: "refunding", shipped: false }),
  row({ order_id: "b5", status_kind: "awaiting_shipment", shipped: false })
];
assert.equal(bulkContext.isSelectable(bulkRows[0]), true, "awaiting shipment can be selected");
assert.equal(bulkContext.isSelectable(bulkRows[1]), false, "already shipped cannot be selected");
assert.equal(bulkContext.isSelectable(bulkRows[2]), false, "shipped status cannot be selected");
assert.equal(bulkContext.isSelectable(bulkRows[3]), false, "refunding cannot be selected");
assert.deepEqual(
  bulkContext.selectableRows(bulkRows).map(item => item.order_id),
  ["b1", "b5"],
  "only currently shippable rows are selectable"
);
assert.deepEqual(
  bulkContext.selectedShipRows(bulkRows, { b1: true, b3: true, b5: true }).map(item => item.order_id),
  ["b1", "b5"],
  "selected set is intersected with selectable rows"
);

const exportStartMarker = "// WEIDIAN_EXPORT_PURE_START";
const exportEndMarker = "// WEIDIAN_EXPORT_PURE_END";
const exportStart = template.indexOf(exportStartMarker);
const exportEnd = template.indexOf(exportEndMarker);
assert.ok(exportStart >= 0 && exportEnd > exportStart, "export pure helper block should exist");

const exportContext = {};
vm.createContext(exportContext);
vm.runInContext(
  template.slice(exportStart + exportStartMarker.length, exportEnd) + `
    this.maskName = maskName;
    this.rowsTotal = rowsTotal;
  `,
  exportContext
);

assert.equal(exportContext.maskName("徐某人"), "徐**", "Chinese names keep first char");
assert.equal(exportContext.maskName("ama"), "a**", "ASCII names keep first char");
assert.equal(exportContext.maskName("A"), "*", "single char becomes one star");
assert.equal(exportContext.maskName("  "), "匿名", "empty names become anonymous");
assert.equal(exportContext.maskName("再坏对你不好吗"), "再**", "mask does not leak name length");
assert.equal(exportContext.rowsTotal([{ amount: "1.20" }, { amount: 2 }, { amount: null }]), 3.2, "filtered total sums amounts");

console.log("weidian orders frontend account filter tests passed");
