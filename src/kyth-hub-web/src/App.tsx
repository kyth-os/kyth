import { Route, Routes, useLocation } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Topbar } from "./components/Topbar";
import { Dashboard } from "./pages/Dashboard";
import { Play } from "./pages/Play";
import { Apps } from "./pages/Apps";
import { ThisPc } from "./pages/ThisPc";
import { MoveIn } from "./pages/MoveIn";
import { Updates } from "./pages/Updates";

const crumbFor: Record<string, string> = {
  "/": "Home",
  "/play": "Play",
  "/apps": "Apps",
  "/this-pc": "This PC",
  "/move-in": "Move In",
  "/updates": "Updates",
};

export function App() {
  const location = useLocation();
  const crumb = crumbFor[location.pathname] ?? "Home";

  return (
    <>
      <div className="bg-glow" />
      <div className="app-shell">
        <Sidebar />
        <main className="scroll-area main-content" style={{ flex: 1, padding: "0 24px 24px", overflowY: "auto" }}>
          <Topbar crumb={crumb} />
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/play" element={<Play />} />
            <Route path="/apps" element={<Apps />} />
            <Route path="/this-pc" element={<ThisPc />} />
            <Route path="/move-in" element={<MoveIn />} />
            <Route path="/updates" element={<Updates />} />
          </Routes>
        </main>
      </div>
    </>
  );
}
