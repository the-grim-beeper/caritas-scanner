import { useState, type FormEvent } from "react";
import { api } from "../api";
import { useLang, useT } from "../i18n";

export function Login({ onDone }: { onDone: () => void }) {
  const t = useT();
  const { lang, setLang } = useLang();
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
      <form onSubmit={submit} className="w-full max-w-md border-t-2 border-ink pt-4">
        <div className="flex justify-between items-start gap-4">
          <h1 className="display text-[1.8rem] leading-tight">{t("app_title")}</h1>
          <button type="button" className="btn btn-quiet !px-2 !py-0.5 text-xs" onClick={() => setLang(lang === "de" ? "en" : "de")}>
            {lang === "de" ? "EN" : "DE"}
          </button>
        </div>
        <p className="text-sm text-ink-2 mt-2 mb-6">{t("app_sub")}</p>
        <label className="label block mb-1" htmlFor="pw">
          {t("password")}
        </label>
        <input id="pw" type="password" className="w-full" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus autoComplete="current-password" />
        {bad && <p className="text-sm mt-2">{t("wrong_password")}</p>}
        <button className="btn btn-fir mt-4" disabled={busy}>
          {t("sign_in")}
        </button>
      </form>
    </main>
  );
}
