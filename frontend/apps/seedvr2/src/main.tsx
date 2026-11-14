import React from "react";
import ReactDOM from "react-dom/client";
import { StudioThemeProvider } from "@colab/shared";
import { SeedVR2StudioApp } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <StudioThemeProvider>
      <SeedVR2StudioApp />
    </StudioThemeProvider>
  </React.StrictMode>
);
