import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { api, AuthError } from "./api";
import { Login } from "./components/Login";
import { Masthead } from "./components/Masthead";
import { LangContext } from "./i18n";
import type { Lang, Meta } from "./types";
import { Calendar } from "./views/Calendar";
import { Coverage } from "./views/Coverage";
import { Digest } from "./views/Digest";
import { Radar } from "./views/Radar";
import { Signals } from "./views/Signals";
import { Watchlist } from "./views/Watchlist";

function readLang(): Lang {
  try {
    const v = localStorage.getItem("rns.lang");
    if (v === "de" || v === "en") return v;
  } catch {
    /* storage unavailable */
  }
  return navigator.language.startsWith("de") ? "de" : "en";
}

export default function App() {
  const [lang, setLangState] = useState<Lang>(readLang);
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);

  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("rns.lang", l);
    } catch {
      /* ignore */
    }
  };

  const load = useCallback(async () => {
    try {
      setMeta(await api.meta());
      setAuthed(true);
    } catch (e) {
      if (e instanceof AuthError) setAuthed(false);
      else setAuthed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);


  return (
    <LangContext.Provider value={{ lang, setLang }}>
      {authed === null ? null : !authed ? (
        <Login onDone={() => void load()} />
      ) : (
        <BrowserRouter>
          <Masthead meta={meta} />
          <main className="max-w-[1400px] mx-auto px-4 md:px-6 pb-16">
            <Routes>
              <Route path="/" element={<Radar meta={meta} />} />
              <Route path="/digest" element={<Digest meta={meta} />} />
              <Route path="/digest/:id" element={<Digest meta={meta} />} />
              <Route path="/signals" element={<Signals meta={meta} />} />
              <Route path="/watchlist" element={<Watchlist meta={meta} />} />
              <Route path="/watchlist/:slug" element={<Watchlist meta={meta} />} />
              <Route path="/calendar" element={<Calendar meta={meta} />} />
              <Route path="/coverage" element={<Coverage meta={meta} />} />
            </Routes>
          </main>
        </BrowserRouter>
      )}
    </LangContext.Provider>
  );
}
