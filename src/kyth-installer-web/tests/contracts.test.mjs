import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const api = await readFile(new URL("../src/api.ts", import.meta.url), "utf8");
const app = await readFile(new URL("../src/InstallerApp.tsx", import.meta.url), "utf8");
const native = await readFile(new URL("../src-tauri/src/native_main.rs", import.meta.url), "utf8");

test("API adapter decodes JSON responses", () => {
  assert.match(api, /JSON\.parse\(text\)/);
  assert.match(api, /payload as T/);
});

test("React compatibility UI projects every destructive mode", () => {
  for (const field of ["target_partition", "resize_gib", "free_region_start", "free_region_end", "confirm_current"]) {
    assert.match(app, new RegExp(`(?:update|onUpdate)\\(\\"${field}\\"`));
  }
  assert.match(app, /result\.ok/);
  assert.match(app, /unsubscribe/);
  assert.match(app, /installerApi\.report/);
});

test("Rust/Slint remains the production installer client", () => {
  assert.match(native, /fn validated_install_plan/);
  assert.match(native, /stream_install_events/);
  assert.match(native, /confirm_current/);
});
