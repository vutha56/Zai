import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import "./styles/tokens.css";
import "./styles/global.css";
import Dashboard from "./pages/Dashboard";
import SignalDetail from "./pages/SignalDetail";
import Backtest from "./pages/Backtest";
import History from "./pages/History";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/signal/:id" element={<SignalDetail />} />
        <Route path="/backtest" element={<Backtest />} />
        <Route path="/history" element={<History />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
