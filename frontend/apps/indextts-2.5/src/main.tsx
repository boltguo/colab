import React from "react";
import ReactDOM from "react-dom/client";
import { StudioThemeProvider } from "@colab/shared";
import { IndexTTSStudioApp } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <StudioThemeProvider>
      <IndexTTSStudioApp />
    </StudioThemeProvider>
  </React.StrictMode>
);
