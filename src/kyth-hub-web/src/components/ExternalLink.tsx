import { openExternalUrl } from "../services/liveData";

/** External hyperlink that opens in the system browser via the backend.
 *
 * Bare `target="_blank"` anchors render inside the trusted Hub webview;
 * this routes the click through the `open_external_url` command (fixed
 * xdg-open argv, https-only) instead. Behaves like a normal link for
 * styling and accessibility.
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
  return (
    <a
      href={href}
      className={className}
      style={style}
      onClick={(event) => {
        event.preventDefault();
        void openExternalUrl(href).catch(() => {
          // The backend reports the failure; the click itself must not
          // navigate the webview anywhere.
        });
      }}
    >
      {children}
    </a>
  );
}
