// Headless construction smoke test for the supported React/Tauri Hub.
//
// A native Tauri window needs a real GTK/WebKit display, so this doesn't
// launch the actual `kyth-hub-shell` binary (that would need Xvfb and is a
// separate, larger follow-up) — it renders every Hub section component
// server-side (`react-dom/server`, via Vite's `ssrLoadModule` so real
// TSX/JSX runs, no jsdom needed) with its real `HubSection` data. That
// exercises the failure class where a section component has an import-time or
// construction-time bug — a
// component that throws the moment React calls it, before any button is
// ever clicked. `useEffect` bodies don't run under SSR, so this doesn't
// catch a bug that only shows up after mount's data fetch resolves; the
// existing Python contract tests and this repo's manual QA cover that.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { createServer } from "vite";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");

// Same section-key -> component extraction as
// tests/test_kyth_hub_web_actions.py's test_every_section_key_has_a_component
// — kept in sync deliberately: if that regex ever changes shape, this one
// should too, so both catch the same class of drift.
async function wiredSections(page) {
  const text = await readFile(resolve(root, "src/pages", page), "utf8");
  const block = text.match(/sectionContent=\{\{(.*?)\}\}/s);
  assert.ok(block, `${page} has no sectionContent map`);
  return [...block[1].matchAll(/(?:^|[{,])\s*(?:"([^"\n]+)"|([\w-]+))\s*:\s*(\w+Section)/gm)]
    .map(([, quoted, bare, component]) => ({ key: quoted ?? bare, component }));
}

test("every Hub section component constructs without throwing (SSR render)", async () => {
  // noExternal: react-router-dom is CJS-only, and Vite's SSR module runner
  // otherwise hands it straight to Node's own resolver, which can't see its
  // named exports — bundling it through Vite's CJS interop instead is what
  // a real build already does for the browser bundle. Scoped to just this
  // package: react/react-dom stay externalized (they're the same
  // react-dom/server instance rendering below, and bundling react itself
  // pulls in dev-runtime internals that assume a real CJS host).
  const server = await createServer({
    root,
    server: { middlewareMode: true },
    appType: "custom",
    ssr: {
      noExternal: ["react-router-dom"],
      // react-router-dom's package.json picks its CJS build (dist/index.js)
      // under Vite's default SSR ("node") resolve condition, which is the
      // half-CJS/half-ESM file that threw above; its real ESM build
      // (dist/index.mjs) is behind the "import" condition instead.
      resolve: { conditions: ["import", "module", "browser", "default"] },
    },
  });
  try {
    const sectionsModule = await server.ssrLoadModule("/src/data/hubSections.ts");
    const pageSectionArrays = {
      "Play.tsx": sectionsModule.PLAY_SECTIONS,
      "Apps.tsx": sectionsModule.APPS_SECTIONS,
      "ThisPc.tsx": sectionsModule.THIS_PC_SECTIONS,
      "MoveIn.tsx": sectionsModule.MOVE_IN_SECTIONS,
      "Updates.tsx": sectionsModule.UPDATES_SECTIONS,
    };

    let rendered = 0;
    const failures = [];
    for (const [page, sections] of Object.entries(pageSectionArrays)) {
      assert.ok(Array.isArray(sections) && sections.length > 0, `${page}'s section array is empty — hubSections.ts import broke`);
      for (const { key, component } of await wiredSections(page)) {
        const section = sections.find((candidate) => candidate.key === key);
        assert.ok(section, `${page} wires "${key}" to ${component} but hubSections.ts has no matching entry`);
        // One try/catch around both the module load and the render: an
        // import-time throw (a broken top-level statement) and a
        // construction-time throw (one inside the component body) are the
        // same failure class this test exists to catch, and catching both
        // here means one broken component doesn't stop the rest of the
        // Hub from being checked in the same run.
        try {
          const mod = await server.ssrLoadModule(`/src/components/${component}.tsx`);
          const Component = mod[component];
          assert.ok(typeof Component === "function", `${component}.tsx has no "${component}" export`);
          renderToStaticMarkup(React.createElement(Component, { section }));
          rendered += 1;
        } catch (err) {
          failures.push(`${page} -> ${component} ("${key}"): ${err instanceof Error ? err.stack : err}`);
        }
      }
    }

    // Dashboard ("Welcome") takes no props and isn't part of a
    // sectionContent map — render it directly, same as the Qt smoke test's
    // MainWindow itself, not just its pages. It (via HeroCard) calls
    // useNavigate(), so it needs router context — MemoryRouter, not the
    // HashRouter main.tsx actually mounts it inside, since HashRouter reads
    // `document.location` unconditionally and isn't SSR-safe by design
    // (real SSR apps use react-router-dom/server's StaticRouter for this
    // exact reason). MemoryRouter gives the same context without a DOM;
    // every other section component above is rendered standalone
    // deliberately, since none of them use a router hook.
    const dashboardMod = await server.ssrLoadModule("/src/pages/Dashboard.tsx");
    const { MemoryRouter } = await server.ssrLoadModule("react-router-dom");
    try {
      renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(dashboardMod.Dashboard)));
      rendered += 1;
    } catch (err) {
      failures.push(`Dashboard: ${err instanceof Error ? err.stack : err}`);
    }

    assert.equal(failures.length, 0, `\n${failures.join("\n\n")}`);
    // 20 sections + Dashboard, per PARITY.md's "27 page keys total (Welcome
    // + 6 landings + 21 sections + 1 Dashboard alias)" — landings (Play,
    // Apps, This PC, Move In, Updates itself as a destination) don't have
    // their own sectionContent component, so 21 + 1 is the right floor here.
    assert.ok(rendered >= 21, `only rendered ${rendered} components — did the extraction regex break?`);
  } finally {
    await server.close();
  }
});
