import { Link, useNavigate, useParams } from "react-router-dom";
import { api, questionsCached } from "../api";
import { BalanceSpark, CitedSignalLine, Empty, Fail, Loading, MovementText, Quote, Section, StrengthMark, TiltBar } from "../components/ui";
import { fmtDate, pick, useLang, useT } from "../i18n";
import type { Direction, JudgementOut, QuestionDetail, QuestionOut } from "../types";
import { useAsync } from "../useAsync";
import { qNumber } from "../useQuestions";

export function Fragen() {
  const { id } = useParams();
  if (id) return <QuestionPage id={id} />;
  return <Ledger />;
}

function Ledger() {
  const { lang } = useLang();
  const t = useT();
  const nav = useNavigate();
  const res = useAsync(() => questionsCached(), []);
  if (res.error) return <Fail error={res.error} retry={res.reload} emptyKey="q_none" />;
  if (!res.data) return <Loading />;
  const qs = [...res.data].sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0) || a.id.localeCompare(b.id));
  if (qs.length === 0) return <Empty k="q_none" />;

  return (
    <div className="fade-in">
      <p className="serif text-[1.15rem] leading-snug pt-6 max-w-[64ch]">{t("q_lead")}</p>

      <table className="data mt-6 hidden md:table">
        <thead>
          <tr>
            <th className="w-10">{t("q_no")}</th>
            <th>{t("q_question")}</th>
            <th className="w-[230px]">{t("q_tilt")}</th>
            <th className="w-[130px]">{t("q_weeks")}</th>
            <th className="w-[100px]" title={t("q_counts_title")}>
              {t("q_evidence")}
            </th>
          </tr>
        </thead>
        <tbody>
          {qs.map((q) => (
            <tr key={q.id} className="cursor-pointer hover:bg-paper-2" onClick={() => nav(`/fragen/${q.id}`)}>
              <td className="display text-lg leading-none pt-3">{qNumber(q.id)}</td>
              <td>
                <Link to={`/fragen/${q.id}`} className="serif text-[1.05rem] leading-snug hover:text-fir" onClick={(e) => e.stopPropagation()}>
                  {pick(q, "title", lang)}
                </Link>
                <div className="text-xs text-ink-3 mt-1">
                  {t("q_driver")}: {pick(q, "driver", lang)}
                </div>
              </td>
              <td>
                <TiltBar q={q} balance={q.balance} movement={q.movement} />
                <MovementText q={q} movement={q.movement} className="block text-xs mt-1" />
              </td>
              <td className="pt-4">
                <BalanceSpark series={q.series ?? []} />
              </td>
              <td className="text-sm num pt-3">
                <Counts q={q} stacked />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* narrow screens: one block per question */}
      <ul className="md:hidden mt-4">
        {qs.map((q) => (
          <li key={q.id} className="rule py-3">
            <Link to={`/fragen/${q.id}`} className="block">
              <span className="label">
                {t("q_no")} {qNumber(q.id)}
              </span>
              <span className="serif block leading-snug">{pick(q, "title", lang)}</span>
            </Link>
            <div className="mt-2 flex flex-wrap items-end gap-4">
              <TiltBar q={q} balance={q.balance} movement={q.movement} />
              <BalanceSpark series={q.series ?? []} />
            </div>
            <div className="text-xs mt-1 flex gap-4">
              <MovementText q={q} movement={q.movement} />
              <span className="text-ink-3 num">
                <Counts q={q} />
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Counts({ q, stacked = false }: { q: QuestionOut; stacked?: boolean }) {
  const t = useT();
  const f = q.counts?.for ?? 0;
  const a = q.counts?.against ?? 0;
  if (stacked)
    return (
      <span title={t("q_counts_title")} className="block leading-snug">
        <span className="block">{t("q_n_for", { n: f })}</span>
        <span className="block">{t("q_n_against", { n: a })}</span>
      </span>
    );
  return <span title={t("q_counts_title")}>{t("q_counts", { f, a })}</span>;
}

function QuestionPage({ id }: { id: string }) {
  const { lang } = useLang();
  const t = useT();
  const res = useAsync(() => api.question(id), [id]);
  if (res.error) return <Fail error={res.error} retry={res.reload} emptyKey="q_none" />;
  if (!res.data) return <Loading />;
  const q = res.data;
  const evidence = q.evidence ?? q.latest ?? [];
  const against = evidence.filter((j) => j.direction === "against");
  const pro = evidence.filter((j) => j.direction === "for");

  return (
    <div className="fade-in">
      <Link to="/fragen" className="link text-sm inline-block pt-5">
        {t("q_all")}
      </Link>
      <header className="mt-3 grid gap-x-10 gap-y-4 lg:grid-cols-[minmax(0,1fr)_380px] items-end">
        <div>
          <p className="label">{t("q_of", { n: qNumber(q.id) })}</p>
          <h2 className="display text-[1.7rem] md:text-[2.1rem] leading-[1.15] mt-1 max-w-[38ch]">{pick(q, "title", lang)}</h2>
          <p className="text-sm text-ink-2 mt-2">
            {t("q_driver")}: {pick(q, "driver", lang)}
          </p>
        </div>
        <div>
          <TiltBar q={q} balance={q.balance} movement={q.movement} size="l" />
          <p className="text-sm mt-2 flex flex-wrap gap-x-4">
            <span>
              <span className="label mr-1.5">{t("q_movement_4w")}</span>
              <MovementText q={q} movement={q.movement} className="font-medium" />
            </span>
            <span className="text-ink-3 num">
              <Counts q={q} />
            </span>
          </p>
        </div>
      </header>

      <div className="grid gap-x-12 lg:grid-cols-2">
        <Section title={t("q_weeks")} hint={t("q_balance_hint")}>
          <BalanceSpark series={q.series ?? []} q={q} size="l" />
        </Section>

        <Section title={t("q_what_counts")}>
          <div className="grid gap-5">
            <Definition label={pick(q, "against_label", lang)} text={pick(q, "against", lang)} side="against" />
            <Definition label={pick(q, "for_label", lang)} text={pick(q, "for", lang)} side="for" />
          </div>
          {q.sources_de && (
            <p className="text-sm text-ink-2 mt-4">
              <span className="label mr-2">{t("q_where")}</span>
              {q.sources_de}
            </p>
          )}
        </Section>
      </div>

      <Section title={t("q_evidence")}>
        <div className="grid gap-x-10 gap-y-8 md:grid-cols-2">
          <EvidenceColumn q={q} side="against" items={against} />
          <EvidenceColumn q={q} side="for" items={pro} />
        </div>
      </Section>
    </div>
  );
}

function Definition({ label, text, side }: { label: string; text: string; side: Direction }) {
  return (
    <div className="border-t border-ink pt-2">
      <h3 className="font-semibold">
        <span className="text-rust mr-1.5" aria-hidden>
          {side === "for" ? "→" : "←"}
        </span>
        {label}
      </h3>
      <p className="text-sm text-ink-2 mt-1 leading-relaxed">{text}</p>
    </div>
  );
}

function EvidenceColumn({ q, side, items }: { q: QuestionDetail; side: Direction; items: JudgementOut[] }) {
  const { lang } = useLang();
  const t = useT();
  const label = pick(q, side === "for" ? "for_label" : "against_label", lang);
  return (
    <div className="min-w-0">
      <h3 className="display text-lg border-b-2 border-ink pb-1 flex items-baseline justify-between gap-3">
        <span>
          <span className="text-rust mr-1.5" aria-hidden>
            {side === "for" ? "→" : "←"}
          </span>
          {label}
        </span>
        <span className="text-sm font-normal text-ink-3 num">{items.length}</span>
      </h3>
      {items.length === 0 ? (
        <p className="text-sm text-ink-3 py-4">{t("q_no_evidence")}</p>
      ) : (
        <ul>
          {items.map((j) => (
            <li key={j.id} className="rule py-4">
              <Quote text={j.quote} className="text-[1.05rem] leading-snug" />
              <p className="text-sm text-ink-2 mt-2 leading-relaxed">{pick(j, "rationale", lang)}</p>
              <div className="mt-2.5">
                <CitedSignalLine s={j.signal} compact />
              </div>
              <div className="text-xs text-ink-3 mt-1.5 flex flex-wrap gap-x-4">
                <StrengthMark strength={j.strength} />
                <span>{fmtDate(j.created_at, lang)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
