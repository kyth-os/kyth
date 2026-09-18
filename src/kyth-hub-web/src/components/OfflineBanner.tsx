import { useEffect, useState } from "react";
import { invalidateAllSharedReads } from "../services/liveData";

/** Parent-facing offline state: Hub reads are local-first, but installs,
 * updates, and catalog search need the network. Without this banner an
 * offline parent retries actions that cannot succeed and reads the failure
 * as a broken system. */
export function OfflineBanner() {
  const [online, setOnline] = useState<boolean>(() =>
    typeof navigator === "undefined" ? true : navigator.onLine !== false,
  );

  useEffect(() => {
    const goOnline = () => { invalidateAllSharedReads(); setOnline(true); };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  if (online) return null;
  return (
    <div
      role="alert"
      className="offline-banner"
      style={{
        margin: "0 0 12px",
        padding: "10px 14px",
        borderRadius: 10,
        border: "1px solid var(--hairline)",
        background: "var(--surface-raised)",
        fontSize: 13,
      }}
    >
      <strong>You are offline.</strong>{" "}
      <span className="card-copy">
        Installed-app status below is current, but installs, updates, and new
        searches need a connection — reconnect and they will work without a
        refresh.
      </span>
    </div>
  );
}
