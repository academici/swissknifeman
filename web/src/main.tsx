import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { tokenStore } from "./features/auth/tokenStore";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";

const initialToken = tokenStore.ingestFragment();
const root = document.getElementById("root");
if (!root) throw new Error("Missing application root");

createRoot(root).render(<StrictMode><App initialToken={initialToken} /></StrictMode>);
