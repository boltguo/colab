import React from "react";
import ReactDOM from "react-dom/client";
import { StudioThemeProvider } from "@colab/shared";
import { QwenChatStudioApp } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <StudioThemeProvider>
      <QwenChatStudioApp />
    </StudioThemeProvider>
  </React.StrictMode>
);
