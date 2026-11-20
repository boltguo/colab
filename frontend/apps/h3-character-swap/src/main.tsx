import React from "react";
import ReactDOM from "react-dom/client";
import { StudioThemeProvider } from "@colab/shared";
import { H3CharacterSwapStudioApp } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <StudioThemeProvider>
      <H3CharacterSwapStudioApp />
    </StudioThemeProvider>
  </React.StrictMode>
);
