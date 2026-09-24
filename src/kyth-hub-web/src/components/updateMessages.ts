export function friendlyAvailabilityDetail(detail: string | undefined, fallback: string): string {
  const lower = (detail ?? "").toLowerCase();
  if (lower.includes("[privileged]")) {
    return "A KythOS helper service isn't running. Update KythOS and restart, then try again.";
  }
  if (lower.includes("privileged service")) {
    return "The system update helper isn't running. Update KythOS and restart, then try again.";
  }
  if (lower.includes("timed out") || lower.includes("timeout") || lower.includes("network") || lower.includes("unavailable")) {
    return "We couldn't reach the update service. Check your internet connection and try again.";
  }
  if (lower.includes("staged") || lower.includes("promoted") || lower.includes("bootloader")) {
    return "The update is downloaded and ready. Restart KythOS to finish installing it.";
  }
  if (lower.includes("up to date") || lower.includes("uptodate") || lower.includes("no_change")) {
    return "KythOS is up to date. No restart is needed.";
  }
  return fallback;
}

export function friendlyAvailabilityResult(state: string, staged: boolean, detail: string | undefined): string {
  if (staged) return "The update is downloaded and ready. Restart KythOS to finish installing it.";
  if (state === "available") return "A KythOS update is available. Choose Download and stage to install it.";
  if (state === "uptodate") return "KythOS is up to date. No restart is needed.";
  return friendlyAvailabilityDetail(detail, "We couldn't complete the update check. Please try again.");
}

export function friendlyActionError(action: string, error: unknown): string {
  const detail = error instanceof Error ? error.message : String(error);
  const lower = detail.toLowerCase();
  const withDetails = (message: string): string => {
    const concise = detail.trim();
    return concise && concise !== message ? `${message} Details: ${concise}` : message;
  };

  if (lower.includes("[privileged]")) {
    const message = action === "stage"
      ? "The update helper couldn't finish. Check update status before retrying."
      : "A KythOS helper service isn't running, so this couldn't finish. Update KythOS and restart, then try again.";
    return action === "stage" ? withDetails(message) : message;
  }
  if (lower.includes("privileged service")) {
    const message = action === "stage"
      ? "The update helper couldn't finish. Check update status before retrying."
      : "The system update helper isn't running, so this couldn't finish. Update KythOS and restart, then try again.";
    return action === "stage" ? withDetails(message) : message;
  }
  if (lower.includes("timed out") || lower.includes("timeout") || lower.includes("network") || lower.includes("unavailable")) {
    if (action === "stage") {
      return withDetails("KythOS couldn't reach the update registry. Check your connection and update status before retrying.");
    }
    return "We couldn't reach the update service. Check your internet connection and try again.";
  }
  if (action === "check") {
    return "We couldn't check for updates. Check your connection and try again.";
  }
  if (action === "stage") {
    if (lower.includes("not enough free disk space") || lower.includes("no space left")) {
      return withDetails("KythOS needs more free disk space before it can stage this update. Check update status before retrying.");
    }
    if (lower.includes("already running") || lower.includes("in progress") || lower.includes("locked")) {
      return withDetails("Another system update is already in progress. Check its status before retrying.");
    }
    return withDetails("KythOS couldn't confirm that the update is staged. Check update status before retrying.");
  }
  if (action === "apps") {
    if (lower.includes("updates remain") || lower.includes("update remains")) {
      return `Some app updates are still pending. Details: ${detail}`;
    }
    if (lower.includes("could not be verified")) {
      return `The update command finished, but Hub couldn't verify whether all app updates are complete. Details: ${detail}`;
    }
    return `We couldn't update every app. Check your connection, then try again. Details: ${detail}`;
  }
  if (action === "apply") {
    return withDetails("The update is ready, but the Hub couldn't request a restart to apply it.");
  }
  if (action === "rollback") {
    return "We couldn't prepare the rollback. Please try again.";
  }
  return "We couldn't complete that update action. Please try again.";
}

export function friendlyActionResult(action: string, detail: string): string {
  const lower = detail.toLowerCase();
  if (lower.includes("cancelled") || lower.includes("canceled")) {
    // A cancelled stage is not a clean no-op: bootc may already have pulled
    // and staged layers before the kill landed, so a restart can still apply
    // staged content. Point at the page state instead of promising nothing.
    if (action === "stage") {
      return "The download was cancelled. Part of the update may already be staged — if this page offers a restart, restarting will still apply that staged content.";
    }
    return "No changes were made.";
  }
  if (action === "stage") {
    if (lower.includes("already running") || lower.includes("latest allowed") || lower.includes("up to date")) {
      return "KythOS is already up to date. No restart is needed.";
    }
    return "The update is downloaded and ready. Restart KythOS to finish installing it.";
  }
  if (action === "apply") {
    return "The restart command was sent. KythOS will finish installing the update as it restarts.";
  }
  if (action === "rollback") {
    return "The rollback is prepared. Restart KythOS to start using the previous system version.";
  }
  return detail;
}
