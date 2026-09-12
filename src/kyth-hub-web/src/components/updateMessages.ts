export function friendlyAvailabilityDetail(detail: string | undefined, fallback: string): string {
  const lower = (detail ?? "").toLowerCase();
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
  if (lower.includes("timed out") || lower.includes("timeout") || lower.includes("network") || lower.includes("unavailable")) {
    if (action === "stage") {
      return "KythOS couldn't reach the update registry before the check timed out. Your current system has not changed.";
    }
    return "We couldn't reach the update service. Check your internet connection and try again.";
  }
  if (action === "stage") {
    if (lower.includes("not enough free disk space") || lower.includes("no space left")) {
      return "KythOS needs more free disk space before it can download this update. Your current system has not changed.";
    }
    if (lower.includes("already running") || lower.includes("in progress") || lower.includes("locked")) {
      return "Another system update is already in progress. Your current system has not changed.";
    }
    return "KythOS couldn't prepare the update. Your current system has not changed.";
  }
  if (action === "apps") {
    return `We couldn't update every app. Check your connection, then try again. Details: ${detail}`;
  }
  if (action === "apply") {
    return "The update is ready, but KythOS couldn't restart to apply it. Please restart from the system menu.";
  }
  if (action === "rollback") {
    return "We couldn't prepare the rollback. Please try again.";
  }
  return "We couldn't complete that update action. Please try again.";
}

export function friendlyActionResult(action: string, detail: string): string {
  const lower = detail.toLowerCase();
  if (lower.includes("cancelled") || lower.includes("canceled")) {
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
