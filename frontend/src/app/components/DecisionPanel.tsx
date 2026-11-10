import { useState } from 'react';
import { CheckCircle2, ExternalLink, FileText, ImageOff, RefreshCw } from 'lucide-react';
import {
  Alternative,
  BOMItem,
  MANUAL_SOURCE,
  ORIGINAL,
  SKIP,
  Selections,
  Verdict,
  lookupReplacement,
  needsDecision,
} from '../utils/BOMConverter';

interface DecisionPanelProps {
  data: BOMItem[];
  selections: Selections;
  onSelect: (index: number, choice: number) => void;
  /** Add (or replace) the user's own pasted replacement for a line. */
  onManual: (index: number, alt: Alternative) => void;
}

export const VERDICT_STYLE: Record<Verdict, { label: string; className: string }> = {
  drop_in: { label: 'Drop-in', className: 'bg-emerald-100 text-emerald-800' },
  check: { label: 'Probably fine, check', className: 'bg-amber-100 text-amber-800' },
  worse: { label: 'Worse spec', className: 'bg-red-100 text-red-800' },
  different_package: { label: 'Different package', className: 'bg-slate-200 text-slate-700' },
  unverified: { label: 'Not compared', className: 'bg-slate-200 text-slate-700' },
};

function price(value: number | null): string {
  return value === null || value === undefined ? '—' : `$${value.toFixed(value < 1 ? 3 : 2)}`;
}

function Photo({ src, alt, size }: { src: string; alt: string; size: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div className={`${size} flex shrink-0 items-center justify-center rounded-lg bg-[#f1f2f5] text-[#a3a8b1]`}>
        <ImageOff className="h-5 w-5" />
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className={`${size} shrink-0 rounded-lg bg-white object-contain`}
    />
  );
}

function SpecDiff({ alt }: { alt: Alternative }) {
  const interesting = alt.specs.filter((s) => s.result !== 'same');
  if (!alt.specs.length) return null;
  return (
    <details className="mt-2 text-xs text-[#4b515c]">
      <summary className="cursor-pointer select-none text-[#2b3039]">
        Spec comparison ({alt.specs.length - interesting.length} same, {interesting.length} different)
      </summary>
      <table className="mt-1 w-full">
        <tbody>
          {alt.specs.map((s) => (
            <tr key={s.name} className="align-top">
              <td className="py-0.5 pr-2 text-[#6b717c]">{s.name}</td>
              <td className="py-0.5 pr-2">{s.original}</td>
              <td
                className={`py-0.5 font-medium ${
                  s.result === 'worse' ? 'text-red-700' : s.result === 'better' ? 'text-emerald-700' : s.result === 'unknown' ? 'text-amber-700' : ''
                }`}
              >
                {s.candidate}
                {s.result === 'unknown' ? ' (not listed)' : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function AlternativeCard({ alt, chosen, onChoose }: { alt: Alternative; chosen: boolean; onChoose: () => void }) {
  const verdict = VERDICT_STYLE[alt.verdict] ?? VERDICT_STYLE.unverified;
  return (
    <div
      className={`flex flex-col rounded-xl border p-3 ${
        chosen ? 'border-[#c91118] bg-[#fff7f7] shadow-[0_0_0_1px_#c91118]' : 'border-black/10 bg-white'
      }`}
    >
      <div className="flex gap-3">
        <Photo src={alt.photo} alt={alt.mpn} size="h-16 w-16" />
        <div className="min-w-0 flex-1">
          <a href={alt.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all font-mono text-sm hover:underline">
            {alt.mpn}
            <ExternalLink className="h-3 w-3 shrink-0" />
          </a>
          <div className="text-xs text-[#6b717c]">{alt.manufacturer}</div>
          <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs ${verdict.className}`}>{verdict.label}</span>
          {alt.source === MANUAL_SOURCE && (
            <span className="ml-1 mt-1 inline-block rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-800">your pick</span>
          )}
        </div>
      </div>
      <div className="mt-2 text-xs text-[#4b515c]">{alt.detail}</div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-[#353b45]">
        <span>{alt.stock.toLocaleString()} in stock</span>
        <span>{price(alt.unit_price)} each</span>
        <span>{alt.packaging}</span>
        {alt.status === 'marketplace' && <span className="text-amber-700">marketplace seller</span>}
        {!alt.orderable && <span className="text-red-700">can't order this qty</span>}
        {alt.datasheet && (
          <a href={alt.datasheet} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 hover:underline">
            <FileText className="h-3 w-3" /> datasheet
          </a>
        )}
      </div>
      <SpecDiff alt={alt} />
      <div className="mt-auto pt-3">
        <button
          type="button"
          disabled={!alt.orderable}
          onClick={onChoose}
          className={`w-full rounded-full px-3 py-1.5 text-xs font-medium ${
            chosen
              ? 'bg-[#c91118] text-white'
              : alt.orderable
                ? 'border border-black/20 bg-white text-[#1f232b] hover:bg-[#efeff2]'
                : 'cursor-not-allowed border border-black/10 text-[#a3a8b1]'
          }`}
        >
          {chosen ? (
            <span className="inline-flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5" /> Using this</span>
          ) : (
            'Use this'
          )}
        </button>
      </div>
    </div>
  );
}

/** Paste a DigiKey link / part number; the backend spec-checks it against the original like the suggestions. */
function ManualEntry({ item, onFound }: { item: BOMItem; onFound: (alt: Alternative) => void }) {
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!query.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      onFound(await lookupReplacement(query.trim(), item));
      setQuery('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Lookup failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3">
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Know a better part? Paste a DigiKey link or part number"
          aria-label="Replacement part"
          className="min-w-0 flex-1 rounded-full border border-black/20 bg-white px-4 py-1.5 text-sm"
        />
        <button
          type="submit"
          disabled={busy || !query.trim()}
          className="inline-flex items-center gap-1 rounded-full border border-black/20 bg-white px-4 py-1.5 text-xs font-medium hover:bg-[#efeff2] disabled:cursor-not-allowed disabled:text-[#a3a8b1]"
        >
          {busy && <RefreshCw className="h-3 w-3 animate-spin" />}
          Check part
        </button>
      </form>
      {error && <p className="mt-1 text-xs text-red-700">{error}</p>}
    </div>
  );
}

export function DecisionPanel({ data, selections, onSelect, onManual }: DecisionPanelProps) {
  const lines = data.map((item, index) => ({ item, index })).filter(({ item }) => needsDecision(item));
  if (lines.length === 0) return null;
  const undecided = lines.filter(({ index }) => (selections[index] ?? ORIGINAL) === ORIGINAL).length;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl tracking-tight text-[#1b1f27]">
          Parts that can't be ordered as specified ({lines.length})
        </h2>
        <p className="mt-1 text-sm text-[#4b515c]">
          Each candidate was compared spec by spec with the original. <b>Drop-ins</b> (same package, every listed spec
          equal or better) were picked automatically; anything else needs your call: pick a suggestion, paste your own
          DigiKey part, or skip the line. The cart CSV unlocks once every line is decided.
          {undecided > 0 && <span className="font-semibold text-red-700"> {undecided} still undecided.</span>}
        </p>
      </div>

      {lines.map(({ item, index }) => {
        const selection = selections[index] ?? ORIGINAL;
        const chosenAlt = selection >= 0 ? item.alternatives[selection] : undefined;
        const state = selection === SKIP
          ? { text: 'Skipped: not ordering this line', className: 'text-slate-600' }
          : chosenAlt
            ? {
                text: `Using ${chosenAlt.mpn}${chosenAlt.verdict === 'drop_in' ? ' (drop-in)' : ' (your choice)'}`,
                className: 'text-emerald-700',
              }
            : { text: 'Undecided: not in the cart yet', className: 'text-red-700' };
        return (
          <section id={`decide-${index}`} key={index} className="rounded-2xl border border-black/10 bg-[#fafbfc] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex gap-3">
                <Photo src={item.card?.photo || ''} alt={item.mpn} size="h-14 w-14" />
                <div>
                  <div className="text-sm">
                    <span className="font-semibold">{item.designators || `Line ${index + 1}`}</span>
                    <span className="mx-2 text-[#a3a8b1]">·</span>
                    <span className="font-mono">{item.mpn}</span>
                    {item.manufacturer && <span className="text-[#6b717c]"> ({item.manufacturer})</span>}
                    <span className="mx-2 text-[#a3a8b1]">·</span>
                    need {item.orderQty}
                  </div>
                  <div className="text-xs text-[#5b616c]">{item.note}</div>
                  <div className="mt-1 flex gap-3 text-xs">
                    {item.card?.url && (
                      <a href={item.card.url} target="_blank" rel="noreferrer" className="hover:underline">DigiKey page</a>
                    )}
                    {item.card?.datasheet && (
                      <a href={item.card.datasheet} target="_blank" rel="noreferrer" className="hover:underline">datasheet</a>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex flex-col items-end gap-1">
                <span className={`text-sm font-medium ${state.className}`}>{state.text}</span>
                <div className="flex gap-2">
                  {selection !== SKIP && (
                    <button
                      type="button"
                      onClick={() => onSelect(index, SKIP)}
                      className="rounded-full border border-black/20 bg-white px-3 py-1 text-xs hover:bg-[#efeff2]"
                    >
                      Skip this line
                    </button>
                  )}
                  {selection !== ORIGINAL && (
                    <button
                      type="button"
                      onClick={() => onSelect(index, ORIGINAL)}
                      className="rounded-full border border-black/20 bg-white px-3 py-1 text-xs hover:bg-[#efeff2]"
                    >
                      Undo choice
                    </button>
                  )}
                </div>
              </div>
            </div>

            {item.alternatives.length > 0 ? (
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {item.alternatives.map((alt, i) => (
                  <AlternativeCard
                    key={`${alt.mpn}-${alt.dkpn}`}
                    alt={alt}
                    chosen={selection === i}
                    onChoose={() => onSelect(index, i)}
                  />
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm text-[#5b616c]">
                No in-stock replacement found on DigiKey. Paste one below, or skip the line (e.g. to buy it elsewhere).
              </p>
            )}

            <ManualEntry item={item} onFound={(alt) => onManual(index, alt)} />
          </section>
        );
      })}
    </div>
  );
}
