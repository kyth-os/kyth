// Pure helpers for how the Hub reads the outcome of a background job. Kept free
// of Tauri imports so tests/job-results.test.mjs can load and run the real code.

/** What a user-cancelled job resolves to. It is a non-error string, so callers
 * that chain several jobs must check for it or they keep going after Cancel. */
export const CANCELLED_RESULT = "Cancelled.";

export function isCancelledResult(result: string): boolean {
  return result === CANCELLED_RESULT;
}

/** Run `install` for each id in order. Stops at the first cancelled job: a
 * cancelled start-pack install used to carry on with the remaining apps and
 * then report the whole pack as installed. Failures still throw. */
export async function installInOrder(
  ids: readonly string[],
  install: (id: string) => Promise<string>,
): Promise<{ installed: string[]; cancelled: boolean }> {
  const installed: string[] = [];
  for (const id of ids) {
    const result = await install(id);
    if (isCancelledResult(result)) return { installed, cancelled: true };
    installed.push(id);
  }
  return { installed, cancelled: false };
}

/** Last-request-wins gate: only the most recently started request may write
 * state, so a slow earlier response cannot overwrite a newer one. */
export function createLatestGate(): { start: () => number; isCurrent: (token: number) => boolean } {
  let latest = 0;
  return {
    start: () => ++latest,
    isCurrent: (token) => token === latest,
  };
}

/** What the PipeWire confirm button shows and whether the preview closes.
 * A failed write must keep the preview open so the user can retry, and must not
 * be described as "outside the Hub shell". */
export function pipewireConfirmOutcome(
  result: { ok: boolean; detail: string } | null,
): { message: string; closePreview: boolean } {
  if (result === null) return { message: "Not available outside the Hub shell.", closePreview: false };
  return { message: result.detail, closePreview: result.ok };
}
