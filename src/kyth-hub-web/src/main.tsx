import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { App } from "./App";
import { installDeepLinkHandling } from "./deepLink";
import "./styles/theme.css";

// HashRouter, not BrowserRouter: this loads from a file:// or a bare
// 127.0.0.1 static file server with no server-side routing to fall back
// to on a deep link (matching how a QWebEngineView/kiosk-Chromium load
// works — see kyth-installer's own launch pattern) — no rewrite rules to
// configure on the Python side.
// A rejected deep-link init must not die silently: without the listener,
// --page launches and single-instance activations do nothing for the whole
// session with no visible cause.
void installDeepLinkHandling().catch((reason) => {
  console.error("Deep-link handling failed to initialize:", reason);
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>,
);
