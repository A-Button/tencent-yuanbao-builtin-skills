import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import "./styles.css";
import "./deck-motion.css";
import "./tarot-table.css";
import "./result-actions.css";
import "./responsive.css";
import "./viewport.css";

const probe=document.createElement('div');
probe.id='viewport-probe';probe.setAttribute('aria-hidden','true');document.body.appendChild(probe);
// Start the first shuffle only after the actual UI fonts are ready.
Promise.allSettled([document.fonts.load('400 22px "Noto Serif SC"'),document.fonts.load('500 14px "Noto Serif SC"')]).then(()=>{
  createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);
});
