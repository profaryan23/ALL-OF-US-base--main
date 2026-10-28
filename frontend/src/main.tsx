import React from "react";
import ReactDOM from "react-dom/client";
import { Storefront } from "./components/storefront";
import "./styles.css";

const rootEl = document.getElementById("storefront-root");
if (rootEl) {
  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <Storefront />
    </React.StrictMode>
  );
}

