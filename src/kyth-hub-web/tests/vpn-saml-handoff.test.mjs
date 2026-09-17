// Regression test for the SAML handoff fix (86bd9a11): after the injected
// script captures an ACS auto-post form, the IdP page's own onload handler
// calling form.submit() again must NOT fall through to the native submit
// (which raced the loopback redirect and lost the cookie).
//
// It extracts the exact `init_script` shipped in commands/vpn.rs and runs it
// under DOM stubs that simulate the onload race — no WebKit needed.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const vpnRs = await readFile(resolve(root, "src-tauri/src/commands/vpn.rs"), "utf8");

function extractInitScript(source) {
  const marker = "let init_script = r#\"";
  const start = source.indexOf(marker);
  assert.ok(start !== -1, "init_script raw string must exist in vpn.rs");
  const end = source.indexOf("\"#", start + marker.length);
  assert.ok(end !== -1, "init_script raw string must terminate");
  return source.slice(start + marker.length, end).replaceAll("__KYTH_VPN_TOKEN__", "test-job-1");
}

// Minimal DOM surface the injected script touches.
function makeHarness(forms) {
  const harness = {
    nativeSubmits: 0,
    redirects: [],
    observers: [],
    listeners: {},
  };
  const listeners = {};
  globalThis.window = {
    location: {
      replace(url) {
        harness.redirects.push(url);
      },
    },
  };
  globalThis.HTMLFormElement = class {
    // Native submit stand-in, captured by the script's override as
    // `original` — like the browser's built-in form submission.
    submit() {
      harness.nativeSubmits += 1;
    }
  };
  globalThis.FormData = class {
    constructor(form) {
      this.fields = form._fields;
    }
    get(name) {
      return this.fields[name] ?? null;
    }
    forEach(fn) {
      for (const [key, value] of Object.entries(this.fields)) fn(value, key);
    }
  };
  globalThis.MutationObserver = class {
    constructor(callback) {
      harness.observers.push(callback);
    }
    observe() {}
  };
  for (const form of forms) {
    form.__kythVpnCaptured = false;
    // Inherit the (script-overridden) submit from the stubbed prototype,
    // like a real DOM form element would.
    Object.setPrototypeOf(form, globalThis.HTMLFormElement.prototype);
    form.matches = (selector) => selector === "form";
    form.closest = () => form;
    form.querySelectorAll = () => [];
  }
  globalThis.document = {
    documentElement: {},
    querySelectorAll: () => forms,
    addEventListener: (type, fn) => {
      listeners[type] = fn;
    },
  };
  harness.listeners = listeners;
  return harness;
}

function cleanupGlobals() {
  for (const key of ["window", "HTMLFormElement", "FormData", "MutationObserver", "document"]) {
    delete globalThis[key];
  }
}

const ACS_ACTION = "https://vpn.example/SAML20/SP/ACS";
const OTHER_ACTION = "https://idp.example/continue";

function acsForm() {
  return {
    _fields: { SAMLResponse: "token123", RelayState: "relay" },
    getAttribute: (name) => (name === "action" ? ACS_ACTION : null),
    action: ACS_ACTION,
  };
}

test("captured ACS form suppresses the repeat onload submit", () => {
  const harness = makeHarness([acsForm()]);
  try {
    eval(extractInitScript(vpnRs));
    // Proactive pass at injection captures the form immediately.
    assert.equal(harness.redirects.length, 1);
    assert.match(harness.redirects[0], /http:\/\/127\.0\.0\.1\/kyth-vpn\/saml-acs\?token=test-job-1/);
    assert.match(harness.redirects[0], /SAMLResponse(%3D|=)token123/);
    // The IdP page's own onload handler submits the same form again. The
    // fixed code reports it captured (true) so the override suppresses the
    // native submit instead of racing the redirect.
    const [form] = globalThis.document.querySelectorAll();
    form.submit();
    assert.equal(harness.nativeSubmits, 0);
    assert.equal(harness.redirects.length, 1);
  } finally {
    cleanupGlobals();
  }
});

test("non-ACS forms pass through to the native submit", () => {
  const other = {
    _fields: { username: "pat" },
    getAttribute: () => OTHER_ACTION,
    action: OTHER_ACTION,
  };
  const harness = makeHarness([other]);
  try {
    eval(extractInitScript(vpnRs));
    assert.equal(harness.redirects.length, 0);
    const [form] = globalThis.document.querySelectorAll();
    form.submit();
    assert.equal(harness.nativeSubmits, 1);
  } finally {
    cleanupGlobals();
  }
});

test("captured marker returns suppress, not ignore", () => {
  // Direct pin of the one-line fix: an already-captured form must read as
  // handled (true), never as "not a SAML form" (false).
  const script = extractInitScript(vpnRs);
  assert.match(script, /if\(form\.__kythVpnCaptured\)return true;/);
});
