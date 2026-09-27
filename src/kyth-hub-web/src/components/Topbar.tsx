import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { IconSearch, IconBell } from "./icons";
import { rankSearchResults, type SearchResult } from "../search";
import { routeForPage } from "../deepLink";
import { fetchGuardianSnapshot } from "../services/liveData";

export function Topbar({ crumb }: { crumb: string }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  // The bell shipped with a permanently-lit unread dot and no source —
  // there is no notification centre in either Hub to port. Guardian's
  // pending recommendations are the one real "needs your attention" count,
  // so the dot now means that and nothing else: no pending items, no dot.
  const [pendingCount, setPendingCount] = useState<number | null>(null);

  const results: SearchResult[] = open ? rankSearchResults(query) : [];

  // Results route through routeForPage, the same resolver the --page
  // deep-link contract uses, so a section reached by search and the same
  // section reached from krunner land on exactly one route.
  const go = (result: SearchResult) => {
    navigate(routeForPage(result.entry.key));
    setQuery("");
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!results.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((current) => (current + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => (current - 1 + results.length) % results.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(results[Math.min(highlight, results.length - 1)]);
    }
  };

  useEffect(() => {
    let cancelled = false;
    fetchGuardianSnapshot().then((snapshot) => {
      if (!cancelled) setPendingCount(snapshot ? snapshot.pendingCount : null);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  return (
    <header
      className="topbar"
    >
      <div>
        <p className="page-eyebrow">
          Kyth Hub / {crumb}
        </p>
        <h1 className="page-title">{crumb}</h1>
      </div>

      <div className="topbar-actions">
        <div ref={boxRef} className="search-shell" style={{ position: "relative" }}>
          <div className="glass search-box">
            <IconSearch width={15} height={15} color="var(--text-faint)" />
            <input
              placeholder="Search Hub…"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setHighlight(0);
                setOpen(true);
              }}
              onFocus={() => setOpen(true)}
              onKeyDown={onKeyDown}
              role="combobox"
              aria-expanded={results.length > 0}
              aria-label="Search settings"
              style={{
                background: "transparent",
                border: "none",
                outline: "none",
                color: "var(--text)",
                fontSize: 13,
                width: "100%",
              }}
            />
          </div>
          {open && query.trim() !== "" && (
            <div
              className="glass"
              role="listbox"
              style={{
                position: "absolute",
                top: "calc(100% + 6px)",
                left: 0,
                width: 320,
                padding: 6,
                borderRadius: 12,
                zIndex: 20,
              }}
            >
              {results.length === 0 && (
                <p className="card-copy" style={{ padding: "8px 10px", fontSize: 12 }}>
                  No matching settings.
                </p>
              )}
              {results.map((result, index) => (
                <button
                  key={result.entry.key}
                  role="option"
                  aria-selected={index === highlight}
                  onMouseEnter={() => setHighlight(index)}
                  onClick={() => go(result)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    width: "100%",
                    padding: "8px 10px",
                    borderRadius: 8,
                    border: "none",
                    cursor: "pointer",
                    textAlign: "left",
                    background: index === highlight ? "var(--surface-overlay)" : "transparent",
                  }}
                >
                  <result.entry.Icon width={15} height={15} color="var(--text-faint)" />
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
                      {result.entry.title}
                    </span>
                    <span style={{ display: "block", fontSize: 11, color: "var(--text-faint)" }}>
                      {result.entry.destination}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          className="glass icon-button"
          aria-label={
            pendingCount === null
              ? "Guardian: checking"
              : pendingCount
              ? `Guardian: ${pendingCount} item${pendingCount === 1 ? "" : "s"} need attention`
              : "Guardian: nothing needs attention"
          }
          onClick={() => navigate(routeForPage("Guardian"))}
          style={{ width: 40, height: 40, display: "grid", placeItems: "center", cursor: "pointer", position: "relative" }}
        >
          <IconBell width={16} height={16} />
          {!!pendingCount && (
            <span
              style={{
                position: "absolute",
                top: 9,
                right: 10,
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--accent-end)",
                boxShadow: "0 0 0 2px var(--surface-solid)",
              }}
            />
          )}
        </button>
      </div>
    </header>
  );
}
