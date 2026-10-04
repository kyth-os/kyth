// Regression test: the Windows-installer dialog's status poll must be able to
// reach its cap.
//
// Every poll that returned a job called setJob() with a NEW object, and the
// effect depended on `job`, so React tore the interval down and rebuilt it
// after each poll. The effect-local `polls` counter restarted at 0 every time,
// so the "still running after several minutes" cap (240 polls) could never
// fire while the backend kept answering "running" -- the dialog polled forever.
//
// The component needs a WebKit window to render, so this checks the effect's
// two contract points in the shipped source and then replays the effect with a
// fake clock and React's dependency rule (skip the effect when deps are equal).
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = await readFile(resolve(here, "../src/components/ExeHandlerDialog.tsx"), "utf8");

function effectBlock() {
  const start = source.indexOf("const jobId = job?.job;");
  const end = source.indexOf("if (!inspection && !error) return null;");
  assert.ok(start !== -1 && end > start, "poll effect must key on job identity (jobId/jobState)");
  return source.slice(start, end);
}

test("poll effect depends on job identity and state, not the job object", () => {
  const block = effectBlock();
  assert.ok(/\[jobId, jobState, pollEpoch\]/.test(block), "deps must be [jobId, jobState, pollEpoch]");
  assert.ok(!/\[job, pollEpoch\]/.test(source), "depending on the whole job object resets the poll counter");
  assert.ok(/MAX_STATUS_POLLS = 240/.test(source), "cap constant must exist");
  assert.ok(block.includes("polls >= MAX_STATUS_POLLS"), "effect must use the cap constant");
  assert.ok(/setJob\(\(current\)/.test(block), "unchanged status must keep the same job object");
});

// Replays the effect: returns how many polls ran and whether the cap fired.
function simulate({ depsOf, keepObjectWhenUnchanged }) {
  let job = { job: "j1", state: "running", detail: "" };
  let error = null;
  let calls = 0;
  const timers = [];
  let cleanup = null;
  let prevDeps = null;

  const effect = () => {
    const deps = depsOf(job);
    if (prevDeps && deps.every((dep, i) => Object.is(dep, prevDeps[i]))) return;
    if (cleanup) cleanup();
    prevDeps = deps;
    if (!job || job.state !== "running") {
      cleanup = null;
      return;
    }
    let polls = 0;
    const jobId = job.job;
    const timer = { dead: false, next: 750 };
    timers.push(timer);
    timer.fn = () => {
      polls += 1;
      if (polls >= 240) {
        timer.dead = true;
        error = "cap";
        return;
      }
      calls += 1;
      const next = { id: jobId, state: "running", detail: "working" };
      const unchanged = job.job === next.id && job.state === next.state && job.detail === next.detail;
      if (!(keepObjectWhenUnchanged && unchanged)) job = { job: next.id, state: next.state, detail: next.detail };
      effect(); // a render follows every setJob
    };
    cleanup = () => { timer.dead = true; };
  };

  effect();
  for (let now = 750; now <= 400 * 750 && !error; now += 750) {
    for (const timer of [...timers]) {
      if (!timer.dead && now >= timer.next) {
        timer.next += 750;
        timer.fn();
      }
    }
  }
  return { calls, error };
}

test("the old dependency list never reaches the cap (the reported bug)", () => {
  const old = simulate({ depsOf: (job) => [job, 0], keepObjectWhenUnchanged: false });
  assert.equal(old.error, null);
  assert.equal(old.calls, 400, "kept polling for every simulated tick");
});

test("the shipped dependency list stops at the cap and reports it once", () => {
  const fixed = simulate({ depsOf: (job) => [job?.job, job?.state, 0], keepObjectWhenUnchanged: true });
  assert.equal(fixed.error, "cap");
  assert.ok(fixed.calls <= 240, `polled ${fixed.calls} times, expected at most 240`);
});
