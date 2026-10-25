import { useState } from "react";
import { openExternalUrl } from "../services/liveData";

/** External hyperlink that opens in the system browser via the backend.
 *
 * Bare `target="_blank"` anchors render inside the trusted Hub webview;
 * this routes the click through the `open_external_url` command (fixed
 * xdg-open argv, https-only) instead. Behaves like a normal link for
 * styling and accessibility. If the open fails, the failure is surfaced
 * inline next to the link — a swallowed rejection was a dead click with
 * no feedback at all.
 */
export function ExternalLink({
  href,
  className,
  style,
  children,
}: {
  href: string;
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}) {
  const [failed, setFailed] = useState(false);
  return (
    <>
      <a
        href={href}
        className={className}
        style={style}
        onClick={(event) => {
          event.preventDefault();
          setFailed(false);
          void openExternalUrl(href).catch(() => {
            // The click itself must not navigate the webview anywhere —
            // but it must not die silently either: flag the failure
            // inline, in the same status voice the sections use.
            setFailed(true);
          });
        }}
      >
        {children}
      </a>
      {failed && (
        <span className="card-copy" role="alert" style={{ fontSize: 12, marginLeft: 8 }}>
          Couldn’t open that link — the system browser didn’t open.
        </span>
      )}
    </>
  );
}
