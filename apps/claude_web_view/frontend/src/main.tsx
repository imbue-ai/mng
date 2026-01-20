import "@radix-ui/themes/styles.css";
import "./styles/index.scss";

import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import { ThemeProvider } from "./components/ThemeProvider";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
