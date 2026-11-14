import React from "react";
import ReactDOM from "react-dom/client";
import { StudioThemeProvider } from "@colab/shared";
import { MiniMaxH3StudioApp } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <StudioThemeProvider>
      <MiniMaxH3StudioApp />
    </StudioThemeProvider>
  </React.StrictMode>
);
