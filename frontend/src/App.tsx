import { lazy, Suspense, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { api, AuthError } from "./api";
import { Login } from "./components/Login";
import { Masthead } from "./components/Masthead";
import { Loading } from "./components/ui";
import { LangContext } from "./i18n";
import type { Lang, Meta } from "./types";
import { Fragen } from "./views/Fragen";
import { Kalender } from "./views/Kalender";
import { Lage } from "./views/Lage";
import { Lagebericht } from "./views/Lagebericht";
import { Quellen } from "./views/Quellen";
import { Signale } from "./views/Signale";

// The network view carries d3-force; load it only when someone opens it.
const Netz = lazy(() => import("./views/Netz").then((m) => ({ default: m.Netz })));

const LANG_KEY = "mhs.lang";

/** German first: the stored choice, else German. */
function readLang(): Lang {
  try {
    const v = localStorage.getItem(LANG_KEY);
    if (v === "de" || v === "en") return v;
  } catch {
    /* storage unavailable */
  }
  return "de";
}

export default function App() {
  const [lang, setLangState] = useState<Lang>(readLang);
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);

  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(LANG_KEY, l);
    } catch {
      /* ignore */
    }
  };

  // Bumped after a successful sign-in to fetch meta again.
  const [session, setSession] = useState(0);

  useEffect(() => {
    let alive = true;
    api
      .meta()
      .then((m) => {
        if (!alive) return;
        setMeta(m);
        setAuthed(true);
      })
      .catch((e: unknown) => {
        if (alive) setAuthed(!(e instanceof AuthError));
      });
    return () => {
      alive = false;
    };
  }, [session]);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return (
    <LangContext.Provider value={{ lang, setLang }}>
      {authed === null ? null : !authed ? (
        <Login onDone={() => setSession((n) => n + 1)} />
      ) : (
        <BrowserRouter>
          <Masthead meta={meta} />
          <main className="max-w-[1400px] mx-auto px-4 md:px-6 pb-20">
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="/" element={<Lage meta={meta} />} />
                <Route path="/fragen" element={<Fragen />} />
                <Route path="/fragen/:id" element={<Fragen />} />
                <Route path="/netz" element={<Netz meta={meta} />} />
                <Route path="/lagebericht" element={<Lagebericht meta={meta} />} />
                <Route path="/lagebericht/:id" element={<Lagebericht meta={meta} />} />
                <Route path="/signale" element={<Signale meta={meta} />} />
                <Route path="/kalender" element={<Kalender meta={meta} />} />
                <Route path="/quellen" element={<Quellen meta={meta} />} />
                {/* template paths, so old links still land somewhere sensible */}
                <Route path="/digest/*" element={<Navigate to="/lagebericht" replace />} />
                <Route path="/signals" element={<Navigate to="/signale" replace />} />
                <Route path="/calendar" element={<Navigate to="/kalender" replace />} />
                <Route path="/coverage" element={<Navigate to="/quellen" replace />} />
                <Route path="/watchlist/*" element={<Navigate to="/netz" replace />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </main>
        </BrowserRouter>
      )}
    </LangContext.Provider>
  );
}
