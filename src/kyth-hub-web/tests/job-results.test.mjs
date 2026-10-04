// Regression tests for how the Hub reads job outcomes. They load the REAL
// src/services/jobResults.ts (bundled with esbuild) rather than a copy.
//
//  - Cancelling a starter-pack install used to keep installing the remaining
//    apps and then report the pack as installed, because a cancelled job
//    resolves to the string "Cancelled." instead of throwing.
//  - A slow earlier ProtonDB lookup could overwrite a newer one.
//  - A failed PipeWire write was reported as "outside the Hub shell" and closed
//    the retry preview.
import assert from "node:assert/strict";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { build } from "esbuild";

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(await mkdtemp(resolve(tmpdir(), "jobresults-")), "jobResults.mjs");
await build({
  entryPoints: [resolve(here, "../src/services/jobResults.ts")],
  outfile: out, bundle: true, format: "esm", platform: "node", logLevel: "silent",
});
const { CANCELLED_RESULT, isCancelledResult, installInOrder, createLatestGate, pipewireConfirmOutcome } =
  await import(pathToFileURL(out).href);

test("cancel stops a starter pack instead of installing the rest", async () => {
  const launched = [];
  const install = async (id) => { launched.push(id); return id === "a" ? CANCELLED_RESULT : "done"; };
  const result = await installInOrder(["a", "b", "c"], install);
  assert.deepEqual(launched, ["a"], "apps after the cancelled one must not start");
  assert.equal(result.cancelled, true);
  assert.deepEqual(result.installed, []);
});

test("a cancel partway through keeps what already installed and stops", async () => {
  const launched = [];
  const install = async (id) => { launched.push(id); return id === "b" ? CANCELLED_RESULT : "done"; };
  const result = await installInOrder(["a", "b", "c"], install);
  assert.deepEqual(launched, ["a", "b"]);
  assert.deepEqual(result, { installed: ["a"], cancelled: true });
});

test("an uncancelled pack installs everything, and a failure still throws", async () => {
  const ok = await installInOrder(["a", "b"], async () => "done");
  assert.deepEqual(ok, { installed: ["a", "b"], cancelled: false });
  await assert.rejects(installInOrder(["a", "b"], async (id) => { if (id === "b") throw new Error("boom"); return "x"; }), /boom/);
});

test("isCancelledResult only matches the cancelled sentinel", () => {
  assert.equal(isCancelledResult("Cancelled."), true);
  assert.equal(isCancelledResult("Guardian health check finished."), false);
});

test("the latest-request gate lets only the newest response write", async () => {
  const gate = createLatestGate();
  const written = [];
  const lookup = async (id, ms) => {
    const token = gate.start();
    await new Promise((r) => setTimeout(r, ms));
    if (gate.isCurrent(token)) written.push(id);
  };
  await Promise.all([lookup("730", 60), lookup("570", 5)]);
  assert.deepEqual(written, ["570"], "the slow earlier lookup must not overwrite the newer one");
});

test("a failed PipeWire apply keeps the preview open; success closes it", () => {
  assert.deepEqual(pipewireConfirmOutcome({ ok: false, detail: "pw-metadata failed" }), { message: "pw-metadata failed", closePreview: false });
  assert.deepEqual(pipewireConfirmOutcome({ ok: true, detail: "Applied" }), { message: "Applied", closePreview: true });
  assert.equal(pipewireConfirmOutcome(null).closePreview, false);
});

test("the components actually use these helpers (no copy-paste drift)", async () => {
  const read = (p) => readFile(resolve(here, "..", p), "utf8");
  const store = await read("src/components/AppStoreSection.tsx");
  assert.match(store, /installInOrder\(/);
  assert.doesNotMatch(store, /for \(const app of pack\.apps\) await install/);
  assert.match(await read("src/components/GuardianSection.tsx"), /isCancelledResult\(outcome\)/);
  assert.match(await read("src/components/PerformanceSection.tsx"), /pipewireConfirmOutcome\(/);
  assert.match(await read("src/components/GamingSection.tsx"), /protonGate\.current\.isCurrent\(token\)/);
  assert.match(await read("src/services/liveData.ts"), /return CANCELLED_RESULT/);
});
