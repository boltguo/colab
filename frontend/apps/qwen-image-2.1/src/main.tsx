import React from "react";
import ReactDOM from "react-dom/client";
import { StudioThemeProvider } from "@colab/shared";
import { QwenImageStudioApp } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <StudioThemeProvider>
      <QwenImageStudioApp />
    </StudioThemeProvider>
  </React.StrictMode>
);
