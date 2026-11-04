import { Download, ShoppingCart, ExternalLink } from 'lucide-react';
import { Button } from './ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table';
import {
  BOMItem,
  ConvertMeta,
  MatchStatus,
  SKIP,
  Selections,
  cartLines,
  chosenPart,
  needsDecision,
} from '../utils/BOMConverter';
import { DecisionPanel, VERDICT_STYLE } from './DecisionPanel';

interface BOMTableProps {
  data: BOMItem[];
  meta: ConvertMeta;
  selections: Selections;
  onSelect: (index: number, choice: number) => void;
  onDownloadCart: () => void;
  onDownloadExcel: () => void;
  onDownloadCSV: () => void;
}

const STATUS_LABEL: Record<MatchStatus, { label: string; className: string }> = {
  ok: { label: 'Ready', className: 'bg-emerald-100 text-emerald-800' },
  marketplace: { label: 'Marketplace seller', className: 'bg-amber-100 text-amber-800' },
  moq: { label: 'Minimum order too high', className: 'bg-red-100 text-red-800' },
  low_stock: { label: 'Not enough stock', className: 'bg-red-100 text-red-800' },
  out_of_stock: { label: 'Out of stock', className: 'bg-red-100 text-red-800' },
  ambiguous: { label: 'Several manufacturers', className: 'bg-red-100 text-red-800' },
  not_found: { label: 'Not found', className: 'bg-red-100 text-red-800' },
  error: { label: 'Lookup error', className: 'bg-red-100 text-red-800' },
  not_a_part: { label: 'Skipped (not a part)', className: 'bg-slate-100 text-slate-600' },
};

function price(value: number | null): string {
  return value === null || value === undefined ? '—' : `$${value.toFixed(value < 1 ? 3 : 2)}`;
}

export function BOMTable({
  data,
  meta,
  selections,
  onSelect,
  onDownloadCart,
  onDownloadExcel,
  onDownloadCSV,
}: BOMTableProps) {
  if (data.length === 0) {
    return null;
  }

  const parts = data.map((item, index) => chosenPart(item, selections[index]));
  const ready = parts.filter((p) => p?.orderable).length;
  const skipped = parts.filter((p) => p === null).length;
  const attention = data.length - ready - skipped;
  const substituted = parts.filter((p) => p?.orderable && p.substituted).length;
  const cartCount = cartLines(data, selections).length;
  const total = data.reduce((sum, item, index) => {
    const part = parts[index];
    return part?.orderable && part.unitPrice !== null ? sum + part.unitPrice * item.orderQty : sum;
  }, 0);

  return (
    <div className="w-full space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl tracking-tight text-[#1b1f27]">
          DigiKey BOM for {meta.boards} board{meta.boards === 1 ? '' : 's'}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onDownloadCart} className="gap-2 rounded-full bg-[#c91118] px-5 text-white hover:bg-[#a40e14]">
            <ShoppingCart className="w-4 h-4" />
            DigiKey cart CSV ({cartCount})
          </Button>
          <Button onClick={onDownloadExcel} variant="outline" className="gap-2 rounded-full border-black/20 bg-white px-5 text-[#1f232b] hover:bg-[#efeff2]">
            <Download className="w-4 h-4" />
            Full Excel
          </Button>
          <Button onClick={onDownloadCSV} variant="outline" className="gap-2 rounded-full border-black/20 bg-white px-5 text-[#1f232b] hover:bg-[#efeff2]">
            <Download className="w-4 h-4" />
            Full CSV
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 text-sm">
        <span className="rounded-full bg-emerald-100 px-3 py-1 text-emerald-800">{ready} ready for the cart</span>
        {substituted > 0 && (
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-800">{substituted} of them substituted</span>
        )}
        {attention > 0 && (
          <a href="#decisions" className="rounded-full bg-red-100 px-3 py-1 text-red-800 hover:underline">
            {attention} undecided (not in cart)
          </a>
        )}
        {skipped > 0 && <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">{skipped} skipped</span>}
        <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">≈ {price(total)} at listed prices</span>
        {meta.api_rate_remaining !== null && meta.api_rate_remaining < 150 && (
          <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-800">
            DigiKey API quota low: {meta.api_rate_remaining} calls left today (a BOM takes ~70)
          </span>
        )}
      </div>

      <div id="decisions">
        <DecisionPanel data={data} selections={selections} onSelect={onSelect} />
      </div>

      <h2 className="pt-2 text-2xl tracking-tight text-[#1b1f27]">Full BOM</h2>
      <div className="overflow-hidden rounded-2xl border border-black/10">
        <div className="overflow-x-auto">
          <Table className="min-w-[66rem] table-fixed">
            <colgroup>
              {/* #, designator, part, qty, DigiKey part, stock, price; status takes the rest */}
              {['2.5rem', '6.5rem', '11rem', '6.5rem', '12rem', '5.5rem', '5rem'].map((w, i) => (
                <col key={i} style={{ width: w }} />
              ))}
              <col />
            </colgroup>
            <TableHeader className="bg-[#eef0f4]">
              <TableRow className="hover:bg-[#eef0f4]">
                {['#', 'Designator', 'Part', 'Qty', 'DigiKey part', 'Stock', 'Unit price', 'Status'].map((h) => (
                  <TableHead key={h} className="whitespace-normal px-3 py-3 text-xs tracking-[0.1em] uppercase text-[#535a66]">
                    {h}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((item, index) => {
                const selection = selections[index] ?? -1;
                const alt = selection >= 0 ? item.alternatives[selection] : undefined;
                const part = parts[index];
                const status = STATUS_LABEL[item.status] ?? STATUS_LABEL.error;
                return (
                  <TableRow key={index} className="border-b border-black/5 align-top odd:bg-[#fafbfc] even:bg-white">
                    <TableCell className="px-3 py-3 text-sm text-[#353b45]">{index + 1}</TableCell>
                    <TableCell className="whitespace-normal px-3 py-3 text-sm text-[#353b45]">
                      {item.designators}
                    </TableCell>
                    <TableCell className="whitespace-normal break-words px-3 py-3 text-sm text-[#353b45]">
                      <div className="font-mono">{item.mpn}</div>
                      <div className="text-xs text-[#6b717c]">{item.manufacturer}</div>
                    </TableCell>
                    <TableCell className="whitespace-normal px-3 py-3 text-sm text-[#353b45]">
                      {meta.boards > 1 ? `${item.qtyPerBoard} × ${meta.boards} = ` : ''}
                      <span className="font-semibold">{item.orderQty}</span>
                    </TableCell>
                    <TableCell className="whitespace-normal px-3 py-3 text-sm text-[#353b45]">
                      {part?.dkpn ? (
                        <a
                          href={alt?.url || item.searchUrl}
                          target="_blank"
                          rel="noreferrer"
                          className={`inline-flex items-center gap-1 break-all font-mono hover:underline ${part.orderable ? '' : 'text-[#9aa0aa] line-through'}`}
                        >
                          {part.dkpn}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        item.searchUrl && (
                          <a href={item.searchUrl} target="_blank" rel="noreferrer" className="text-xs hover:underline">
                            search DigiKey
                          </a>
                        )
                      )}
                      <div className="text-xs text-[#6b717c]">{part?.packaging}</div>
                    </TableCell>
                    <TableCell className="px-3 py-3 text-sm text-[#353b45]">
                      {alt ? alt.stock.toLocaleString() : item.stock}
                    </TableCell>
                    <TableCell className="px-3 py-3 text-sm text-[#353b45]">{price(part?.unitPrice ?? null)}</TableCell>
                    <TableCell className="whitespace-normal px-3 py-3 text-sm text-[#353b45]">
                      <span className={`rounded-full px-2 py-0.5 text-xs ${status.className}`}>{status.label}</span>
                      {item.note && <div className="mt-1 text-xs text-[#5b616c]">{item.note}</div>}
                      {needsDecision(item) && (
                        <div className="mt-1 text-xs">
                          {selection === SKIP ? (
                            <span className="text-slate-600">Skipped by you</span>
                          ) : alt ? (
                            <span className="text-emerald-700">
                              → {alt.mpn}{' '}
                              <span className={`rounded-full px-1.5 ${VERDICT_STYLE[alt.verdict]?.className ?? ''}`}>
                                {VERDICT_STYLE[alt.verdict]?.label ?? alt.verdict}
                              </span>
                            </span>
                          ) : (
                            <span className="text-red-700">Undecided</span>
                          )}{' '}
                          <a href={`#decide-${index}`} className="text-[#2b3039] underline">
                            {alt || selection === SKIP ? 'change' : 'decide'}
                          </a>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="text-right text-xs text-[#6b717c]">
        Part numbers from "{meta.mpn_column}"
        {meta.part_number_column ? ` (fallback "${meta.part_number_column}")` : ''}, quantities from{' '}
        {meta.qty_column ? `"${meta.qty_column}"` : 'designator counts'} · {meta.api_calls} DigiKey API calls
        {meta.api_rate_remaining !== null ? `, ${meta.api_rate_remaining} left in DigiKey quota` : ''}
      </div>
    </div>
  );
}
