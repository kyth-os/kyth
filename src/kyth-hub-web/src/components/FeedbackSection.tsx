import { useEffect, useState } from "react";
import type { HubSection } from "../data/hubSections";
import {
  fetchBootcSnapshot,
  fetchGuardianSnapshot,
  fetchKernelFlavor,
  invokeOpenFeedbackIssue,
  type BootcSnapshot,
  type GuardianSnapshot,
} from "../services/liveData";
import { LiveSectionCard, SectionFallbackNote } from "./LiveSectionCard";
import { ActionButton, ActionStatus, useSectionAction } from "./SectionActions";

/** The system details worth attaching to a report — deliberately only what
 * is already visible elsewhere in the Hub (channel, version, kernel, and
 * how many Guardian items are outstanding). Nothing here is collected
 * specially for the report, and the user sees the exact text before it
 * leaves: the send path opens a prefilled GitHub issue in the browser
 * rather than posting anything itself. */
function detailsBlock(bootc: BootcSnapshot | null, kernel: string | null, guardian: GuardianSnapshot | null): string {
  const lines = [
    `Channel: ${bootc?.channel ?? "unknown"}`,
    `Version: ${bootc?.booted?.version ?? "unknown"}`,
    `Kernel flavor: ${kernel ?? "unknown"}`,
    `Guardian pending: ${guardian?.pendingCount ?? "unknown"}`,
  ];
  return lines.join("\n");
}

// "This PC > Feedback" — writes the report, attaches the same system
// details the Hub already shows, and hands it to the browser as a
// prefilled kyth-os/kyth issue (see main.rs's open_feedback_issue, which
// fixes the host and repo so only the text travels).
export function FeedbackSection({ section }: { section: HubSection }) {
  const [snap, setSnap] = useState<GuardianSnapshot | null>(null);
  const [bootc, setBootc] = useState<BootcSnapshot | null>(null);
  const [kernel, setKernel] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [includeDetails, setIncludeDetails] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const { status, busy, run } = useSectionAction();

  useEffect(() => {
    let c = false;
    Promise.all([fetchGuardianSnapshot(), fetchBootcSnapshot(), fetchKernelFlavor()]).then(([g, b, k]) => {
      if (!c) {
        setSnap(g);
        setBootc(b);
        setKernel(k);
        setLoaded(true);
      }
    });
    return () => {
      c = true;
    };
  }, []);

  const details = detailsBlock(bootc, kernel, snap);
  const fieldStyle = {
    width: "100%",
    marginTop: 8,
    padding: "9px 12px",
    borderRadius: 10,
    border: "1px solid var(--hairline)",
    background: "var(--card)",
    fontSize: 13,
    fontFamily: "inherit",
  } as const;

  return (
    <LiveSectionCard section={section} live={snap !== null || bootc !== null}>
      {loaded ? (
        <div style={{ marginTop: 20 }}>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="One line: what went wrong?"
            style={fieldStyle}
          />
          <textarea
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder="What were you doing, and what did you expect to happen instead?"
            rows={5}
            style={{ ...fieldStyle, resize: "vertical" }}
          />

          <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 12.5 }}>
            <input
              type="checkbox"
              checked={includeDetails}
              onChange={(event) => setIncludeDetails(event.target.checked)}
            />
            Attach these system details
          </label>
          <pre
            className="card-copy"
            style={{
              fontSize: 12,
              marginTop: 8,
              padding: "10px 12px",
              border: "1px solid var(--hairline)",
              borderRadius: 10,
              whiteSpace: "pre-wrap",
              opacity: includeDetails ? 1 : 0.5,
            }}
          >
            {details}
          </pre>
        </div>
      ) : (
        <SectionFallbackNote loaded={loaded} />
      )}

      <div style={{ marginTop: 20, borderTop: "1px solid var(--hairline)", paddingTop: 16 }}>
        <p className="card-copy" style={{ fontSize: 12, margin: "0 0 12px" }}>
          This opens a prefilled issue on github.com/kyth-os/kyth in your browser — nothing is sent until you post it
          there.
        </p>
        <ActionButton
          label={busy === "send" ? "Opening…" : "Write this up on GitHub"}
          disabled={busy !== null || title.trim().length === 0}
          onClick={() =>
            run("send", "Opening your browser…", () =>
              invokeOpenFeedbackIssue(title.trim(), includeDetails ? `${body}\n\n---\n${details}` : body),
            )
          }
        />
        <ActionStatus status={status} />
      </div>
    </LiveSectionCard>
  );
}
