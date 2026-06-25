import React from "react";
import ReactDOM from "react-dom/client";

// Bundled, self-hosted variable fonts (no CDN) so the UI renders identically
// on every machine and works fully offline inside the Tauri shell.
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";

import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
