import { lazy, Suspense, Component, type ReactNode } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Topbar } from "./components/Topbar";
import { OfflineBanner } from "./components/OfflineBanner";
import { ExeHandlerDialog } from "./components/ExeHandlerDialog";

const Dashboard = lazy(() => import("./pages/Dashboard").then(({ Dashboard: page }) => ({ default: page })));
const Play = lazy(() => import("./pages/Play").then(({ Play: page }) => ({ default: page })));
const Apps = lazy(() => import("./pages/Apps").then(({ Apps: page }) => ({ default: page })));
const DevTools = lazy(() => import("./pages/DevTools").then(({ DevTools: page }) => ({ default: page })));
const ThisPc = lazy(() => import("./pages/ThisPc").then(({ ThisPc: page }) => ({ default: page })));
const MoveIn = lazy(() => import("./pages/MoveIn").then(({ MoveIn: page }) => ({ default: page })));
const Vpn = lazy(() => import("./pages/Vpn").then(({ Vpn: page }) => ({ default: page })));
const Updates = lazy(() => import("./pages/Updates").then(({ Updates: page }) => ({ default: page })));

/** Catches lazy-chunk load failures (partial update, stale cache) that
 * Suspense alone leaves on "Loading Hub page…" forever. Keyed by pathname
 * so navigating resets it; the retry reloads the whole shell for a clean
 * chunk state. */
class RouteErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }
  render(): ReactNode {
    if (this.state.failed) {
      return (
        <div className="glass dashboard-card card-copy" role="alert">
          <p>This page failed to load. An update may have left cached files behind.</p>
          <button className="primary" onClick={() => window.location.reload()}>Reload Hub</button>
        </div>
      );
    }
    return this.props.children;
  }
}

/** Friendly landing for an unknown path (stale deep link, mistyped
 * hash route): an explanation inside the shell instead of a blank
 * page under a "Home" crumb. */
function PageNotFound() {
  const navigate = useNavigate();
  return (
    <div className="glass dashboard-card card-copy" role="alert">
      <p>This Hub page doesn&apos;t exist — the address may be stale or mistyped.</p>
      <button className="primary" onClick={() => navigate("/")}>Go to Home</button>
    </div>
  );
}

const crumbFor: Record<string, string> = {
  "/": "Home",
  "/play": "Play",
  "/apps": "Apps",
  "/dev-tools": "Dev Tools",
  "/this-pc": "This PC",
  "/move-in": "Move In",
  "/vpn": "VPN",
  "/updates": "Updates",
};

export function App() {
  const location = useLocation();
  const crumb = crumbFor[location.pathname] ?? "Not found";

  return (
    <>
      <div className="bg-glow" />
      <div className="app-shell">
        <Sidebar />
        <main className="scroll-area main-content" style={{ flex: 1, padding: "0 24px 24px", overflowY: "auto" }}>
          <Topbar crumb={crumb} />
          <OfflineBanner />
          {/* A failed chunk import (partial update, stale cache) must offer
            a retry instead of hanging on the Suspense fallback forever. */}
          <RouteErrorBoundary key={location.pathname}>
            <Suspense fallback={<div className="glass dashboard-card card-copy">Loading Hub page…</div>}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/play" element={<Play />} />
              <Route path="/apps" element={<Apps />} />
              <Route path="/dev-tools" element={<DevTools />} />
              <Route path="/this-pc" element={<ThisPc />} />
              <Route path="/move-in" element={<MoveIn />} />
              <Route path="/vpn" element={<Vpn />} />
              <Route path="/updates" element={<Updates />} />
              <Route path="*" element={<PageNotFound />} />
            </Routes>
          </Suspense>
          </RouteErrorBoundary>
        </main>
      </div>
      <ExeHandlerDialog />
    </>
  );
}
