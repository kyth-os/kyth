import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

// Mount the shipped component and API adapter, mocking only the native bridge.
// No display, live NetworkManager, browser online event, or credentials needed.
const require = createRequire(import.meta.url);
function compile(path, suffix = "") {
  return ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8") + suffix, {
    fileName: path,
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  }).outputText;
}
const apiCode = compile("../src/api.ts");
const appCode = compile("../src/InstallerApp.tsx", "\nexports.NetworkStep = NetworkStep;");
function load(code, stubs) {
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module, exports: module.exports, Error, console, setTimeout, clearTimeout,
    require: (id) => {
      if (Object.hasOwn(stubs, id)) return stubs[id];
      if (id === "react" || id === "react/jsx-runtime") return require(id);
      throw new Error(`Unexpected module: ${id}`);
    },
  });
  return module.exports;
}
const ap = { ssid: "Back\\slash:Lab <guest>", security: "--", signal: 80, in_use: false, bssid: "02:00:00:00:00:01", device: "wlan0" };
const result = (status, networks = [], detail = "") => ({ status, networks, detail });
const nodeText = (node) => typeof node === "string" ? node : (Array.isArray(node) ? node : node?.children ?? []).map(nodeText).join("");
function mount({ online = false } = {}) {
  const h = { scan: async () => result("ready", [ap]), connect: async () => {}, calls: [], continued: 0, shell: true };
  const { installerApi } = load(apiCode, {
    "@tauri-apps/api/core": { invoke: async (command, args) => {
      h.calls.push({ command, args });
      if (command === "installer_wifi_networks") return h.scan();
      if (command === "installer_connect_wifi") return h.connect(args);
      throw new Error(`Unexpected command: ${command}`);
    } },
    "@tauri-apps/api/event": { listen: () => { throw new Error("Unexpected event listener"); } },
    "./services/tauriEnv": { inTauriShell: () => h.shell },
  });
  const { NetworkStep } = load(appCode, { "./api": { installerApi, InstallerApiError: class extends Error {} }, "./software": {} });
  act(() => { h.ui = TestRenderer.create(React.createElement(NetworkStep, { online, onNext: () => h.continued++ })); });
  h.api = installerApi;
  h.text = () => nodeText(h.ui.toJSON());
  h.buttons = () => h.ui.root.findAllByType("button");
  h.button = (label) => {
    const found = h.buttons().find((button) => nodeText(button).includes(label));
    assert.ok(found, `Missing button: ${label}. Visible: ${h.text()}`);
    return found;
  };
  h.tiles = () => h.buttons().filter((button) => button.props.className === "tile");
  h.click = async (label) => { await act(async () => { h.button(label).props.onClick(); }); };
  h.close = () => act(() => h.ui.unmount());
  return h;
}

test("structured ready scan renders an open AP with its exact escaped SSID", async () => {
  const h = mount();
  try {
    assert.match(h.text(), /Scan to list nearby Wi-Fi networks/);
    await h.click("Scan for Wi-Fi");
    assert.equal(h.tiles().length, 1);
    assert.equal(nodeText(h.tiles()[0].findByType("strong")), ap.ssid);
    assert.match(nodeText(h.tiles()[0]), /Open network/);
    assert.doesNotMatch(nodeText(h.tiles()[0]), /connected/);
    assert.doesNotMatch(h.text(), /Scan to list nearby Wi-Fi networks/);
  } finally { h.close(); }
});

test("failed rescan clears old selectable APs and reports failure, not an empty or initial scan", async () => {
  const h = mount();
  try {
    await h.click("Scan for Wi-Fi");
    assert.equal(h.tiles().length, 1);
    h.scan = async () => { throw new Error("NetworkManager unavailable"); };
    await h.click("Scan for Wi-Fi");
    assert.equal(h.tiles().length, 0, "failed rescan must invalidate old AP selections");
    assert.match(h.text(), /Wi-Fi scan failed/);
    assert.match(h.text(), /NetworkManager unavailable/);
    assert.match(h.text(), /[Rr]etry/);
    assert.doesNotMatch(h.text(), /Scan to list nearby|No nearby Wi-Fi networks|Scan complete/);
    assert.equal(h.button("Scan for Wi-Fi").props.disabled, false);
    h.scan = async () => result("ready", [ap]);
    await h.click("Scan for Wi-Fi");
    assert.equal(h.tiles().length, 1);
    assert.doesNotMatch(h.text(), /Wi-Fi scan failed|NetworkManager unavailable/);
  } finally { h.close(); }
});

test("scan and terminal launch are mutually exclusive, including rapid duplicate clicks", async () => {
  const h = mount();
  let finishScan, finishConnect;
  try {
    await h.click("Scan for Wi-Fi");
    const staleTileClick = h.tiles()[0].props.onClick;
    const scanClick = h.button("Scan for Wi-Fi").props.onClick;
    h.scan = () => new Promise((resolve) => { finishScan = resolve; });
    await act(async () => { scanClick(); scanClick(); staleTileClick(); });
    assert.equal(h.calls.filter((call) => call.command === "installer_wifi_networks").length, 2, "one initial scan plus one pending rescan");
    assert.equal(h.calls.filter((call) => call.command === "installer_connect_wifi").length, 0);
    assert.equal(h.button("Scanning…").props.disabled, true);
    assert.equal(h.button("Refresh connection status").props.disabled, true);
    assert.match(h.text(), /Scanning for nearby Wi-Fi/);
    assert.equal(h.tiles().length, 0);
    assert.equal(h.button("Continue").props.disabled, false);
    await act(async () => { finishScan(result("ready", [ap])); });
    h.connect = () => new Promise((resolve) => { finishConnect = resolve; });
    const tileClick = h.tiles()[0].props.onClick;
    await act(async () => { tileClick(); tileClick(); });
    assert.equal(h.calls.filter((call) => call.command === "installer_connect_wifi").length, 1);
    assert.equal(h.button("Scan for Wi-Fi").props.disabled, true);
    assert.ok(h.tiles().every((tile) => tile.props.disabled));
    await h.click("Scan for Wi-Fi");
    assert.equal(h.calls.filter((call) => call.command === "installer_wifi_networks").length, 2);
    await act(async () => { finishConnect(); });
    assert.equal(h.button("Scan for Wi-Fi").props.disabled, false);
    assert.ok(h.tiles().every((tile) => !tile.props.disabled));
  } finally { h.close(); }
});

test("same-SSID APs keep distinct BSSID/device identities and send the entire selected row", async () => {
  const h = mount();
  const secure = { ...ap, security: "WPA2", bssid: "02:00:00:00:00:02" };
  const secondDevice = { ...ap, device: "wlan1" };
  const warnings = [];
  const originalError = console.error;
  try {
    h.scan = async () => result("ready", [ap, secure, secondDevice]);
    console.error = (...args) => warnings.push(args.join(" "));
    await h.click("Scan for Wi-Fi");
    console.error = originalError;
    assert.equal(h.tiles().length, 3);
    assert.deepEqual(warnings, [], "same labels must not produce duplicate React keys");
    assert.match(nodeText(h.tiles()[0]), /Open network/);
    assert.match(nodeText(h.tiles()[1]), /WPA2/);
    for (const [index, selected] of [[1, secure], [2, secondDevice]]) {
      assert.equal(nodeText(h.tiles()[index].findByType("strong")), selected.ssid);
      await act(async () => { h.tiles()[index].props.onClick(); });
      const call = h.calls.at(-1);
      assert.equal(call.command, "installer_connect_wifi");
      assert.deepEqual(Object.keys(call.args), ["selected"]);
      assert.equal(call.args.selected, selected);
    }
  } finally { console.error = originalError; h.close(); }
});

test("Konsole launch failure stays visible and selecting the AP again retries", async () => {
  const h = mount();
  try {
    await h.click("Scan for Wi-Fi");
    h.connect = async () => { throw new Error("Could not open the Wi-Fi connection terminal: Konsole missing"); };
    await h.click(ap.ssid);
    assert.match(h.text(), /Konsole missing/);
    assert.match(h.text(), /[Rr]etry.*selecting the network again/);
    assert.doesNotMatch(h.text(), /A terminal opened/);
    assert.equal(h.button("Scan for Wi-Fi").props.disabled, false);
    assert.equal(h.tiles()[0].props.disabled, false);
    h.connect = async () => {};
    await h.click(ap.ssid);
    assert.match(h.text(), /A terminal opened/);
    assert.doesNotMatch(h.text(), /Konsole missing/);
    assert.equal(h.calls.filter((call) => call.command === "installer_connect_wifi").length, 2);
  } finally { h.close(); }
});

test("terminal launch and browser online state do not assert Wi-Fi success; refresh reads connected state", async () => {
  const h = mount({ online: true });
  try {
    assert.match(h.text(), /does not confirm Wi-Fi/);
    await h.click("Scan for Wi-Fi");
    await h.click(ap.ssid);
    assert.match(h.text(), /A terminal opened/);
    assert.ok(h.text().includes(`“${ap.ssid}”`));
    assert.match(h.text(), /success or failure.*terminal/);
    assert.match(h.text(), /does not confirm a Wi-Fi connection/);
    assert.match(h.text(), /[Ii]f it fails.*retry/);
    assert.doesNotMatch(nodeText(h.tiles()[0]), /connected/);
    assert.equal(h.ui.root.findAllByType("input").length, 0, "Wi-Fi passwords never enter the webview");
    const refresh = h.button("Refresh connection status");
    assert.equal(refresh.props.disabled, false);
    h.scan = async () => result("ready", [{ ...ap, in_use: true }]);
    await h.click("Refresh connection status");
    assert.match(nodeText(h.tiles()[0]), /connected/);
    assert.doesNotMatch(h.text(), /A terminal opened/);
    h.scan = async () => result("ready", [ap]);
    await h.click("Refresh connection status");
    assert.doesNotMatch(nodeText(h.tiles()[0]), /connected/);
  } finally { h.close(); }
});

for (const [status, message] of [
  ["empty", /No nearby Wi-Fi networks were found/],
  ["no_adapter", /No Wi-Fi radio was detected/],
  ["radio_disabled", /Wi-Fi radio is off/],
  ["unavailable", /Wi-Fi scanning is unavailable/],
]) {
  test(`completed ${status} scan has a distinct explanation and allows Ethernet continue`, async () => {
    const h = mount({ online: true });
    try {
      h.scan = async () => result(status, [], `Diagnostic: ${status} <safe>`);
      await h.click("Scan for Wi-Fi");
      assert.match(h.text(), message);
      assert.ok(h.text().includes(`Diagnostic: ${status} <safe>`));
      assert.doesNotMatch(h.text(), /Scan to list nearby Wi-Fi networks/);
      assert.equal(h.tiles().length, 0);
      assert.equal(h.button("Scan for Wi-Fi").props.disabled, false);
      assert.equal(h.button("Continue").props.disabled, false);
      assert.match(h.text(), /Ethernet/);
      if (status === "no_adapter") {
        assert.match(h.text(), /virtual Ethernet/);
        assert.doesNotMatch(h.text(), /virtual machine|\bVM\b/);
      }
      await h.click("Continue");
      assert.equal(h.continued, 1);
    } finally { h.close(); }
  });
}
