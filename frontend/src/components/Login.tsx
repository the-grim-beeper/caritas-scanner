import { useState, type FormEvent } from "react";
import { api } from "../api";
import { useT } from "../i18n";

export function Login({ onDone }: { onDone: () => void }) {
  const t = useT();
  const [pw, setPw] = useState("");
  const [bad, setBad] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setBad(false);
    try {
      await api.login(pw);
      onDone();
    } catch {
      setBad(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm border-t-2 border-ink pt-4">
        <h1 className="display text-2xl">{t("app_title")}</h1>
        <p className="text-sm text-ink-3 mt-1 mb-6">{t("app_sub")}</p>
        <label className="eyebrow block mb-1" htmlFor="pw">
          {t("password")}
        </label>
        <input id="pw" type="password" className="w-full" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
        {bad && <p className="text-warn text-sm mt-2">{t("wrong_password")}</p>}
        <button className="btn mt-4" disabled={busy}>
          {t("sign_in")}
        </button>
      </form>
    </main>
  );
}
