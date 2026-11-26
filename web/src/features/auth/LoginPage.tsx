import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { ApiError } from "../../api/errors";
import { useAuth } from "../../app/providers/AuthProvider";

function loginMessage(failure: unknown, invalid: string, forbidden: string, fallback: string): string {
  if (failure instanceof TypeError) return failure.message;
  if (failure instanceof ApiError && failure.status === 401) return invalid;
  if (failure instanceof ApiError && (failure.status === 403 || failure.status === 429)) return forbidden;
  return fallback;
}

export default function LoginPage() {
  const { me, status, signIn, signInWithPassword, continueLocal } = useAuth();
  const [pending, setPending] = useState<"token" | "password" | "local" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submitToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const token = new FormData(form).get("token");
    form.reset();
    if (typeof token !== "string" || !token.trim()) {
      setError("Введите токен доступа");
      return;
    }
    setPending("token");
    setError(null);
    try {
      await signIn(token);
    } catch (failure) {
      setError(loginMessage(
        failure,
        "Токен недействителен или срок его действия истёк.",
        "Запрос отклонён. Повторите вход.",
        "Не удалось проверить токен. Повторите вход.",
      ));
    } finally {
      setPending(null);
    }
  }

  async function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const password = new FormData(form).get("password");
    form.reset();
    if (typeof password !== "string" || !password.trim()) {
      setError("Введите пароль");
      return;
    }
    setPending("password");
    setError(null);
    try {
      await signInWithPassword(password);
    } catch (failure) {
      setError(loginMessage(
        failure,
        "Пароль недействителен.",
        "Запрос отклонён. Повторите вход.",
        "Не удалось войти. Повторите попытку.",
      ));
    } finally {
      setPending(null);
    }
  }

  async function submitLocal() {
    setPending("local");
    setError(null);
    try {
      const entered = await continueLocal();
      if (!entered) setError("Локальный доступ недоступен. Войдите токеном или паролем.");
    } catch {
      setError("Не удалось проверить локальный доступ.");
    } finally {
      setPending(null);
    }
  }

  if (me) return <Navigate to="/" replace />;

  return (
    <main className="login">
      <h1>Вход в SKM</h1>
      {status === "probing" && pending === null && error === null && <p role="status">Проверка сеанса…</p>}
      <form method="post" onSubmit={(event) => { void submitToken(event); }}>
        <label htmlFor="token">Токен доступа</label>
        <input id="token" name="token" type="password" autoComplete="off" disabled={pending !== null} />
        <button type="submit" disabled={pending !== null}>{pending === "token" ? "Проверка…" : "Войти"}</button>
      </form>
      <form method="post" onSubmit={(event) => { void submitPassword(event); }}>
        <label htmlFor="password">Пароль администратора</label>
        <input id="password" name="password" type="password" autoComplete="current-password" disabled={pending !== null} />
        <button type="submit" disabled={pending !== null}>{pending === "password" ? "Проверка…" : "Войти по паролю"}</button>
      </form>
      <button type="button" disabled={pending !== null} onClick={() => { void submitLocal(); }}>
        {pending === "local" ? "Проверка…" : "Продолжить локальный сеанс"}
      </button>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
