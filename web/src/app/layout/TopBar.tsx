import { useState } from "react";
import { Link } from "react-router";
import { escapeText } from "../../lib/safeText";
import { useAuth } from "../providers/AuthProvider";
import { ConnectionBadge } from "./ConnectionBadge";
import { InboxCounter } from "./InboxCounter";
import { ScopeSwitcher } from "./ScopeSwitcher";

export function TopBar() {
  const { me, mode, reloadSession, signOut, logoutError, sessionActionPending } = useAuth();
  const [reloadError, setReloadError] = useState<string | null>(null);

  async function reload() {
    setReloadError(null);
    try {
      await reloadSession();
    } catch {
      setReloadError("Не удалось обновить сеанс.");
    }
  }

  return (
    <header className="top-bar">
      <Link to="/" className="brand">SKM</Link>
      <ScopeSwitcher />
      <div className="session-controls">
        <ConnectionBadge />
        <InboxCounter />
        {me && <bdi className="principal">{escapeText(me.principal.display_name)}</bdi>}
        {mode === "admin_login" && <button type="button" disabled={sessionActionPending} onClick={() => reload()}>Обновить сеанс</button>}
        <button type="button" disabled={sessionActionPending} onClick={() => { void signOut(); }}>Выйти</button>
        {logoutError && <p role="alert">{logoutError}</p>}
        {reloadError && <p role="alert">{reloadError}</p>}
      </div>
    </header>
  );
}
