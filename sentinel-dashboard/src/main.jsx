import React from "react";
import { createRoot } from "react-dom/client";
import SentinelDashboard from "./SentinelDashboard.jsx";
import "./SentinelDashboard.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <SentinelDashboard />
  </React.StrictMode>,
);
