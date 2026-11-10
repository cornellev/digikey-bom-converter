import Papa from 'papaparse';

export const BACKEND_BASE = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5000';

export interface AuthStatus {
  configured: boolean;
  has_refresh_token: boolean;
}

export type MatchStatus =
  | 'ok'
  | 'marketplace'
  | 'moq'
  | 'low_stock'
  | 'out_of_stock'
  | 'ambiguous'
  | 'not_found'
  | 'not_a_part'
  | 'error';

/** Lines with these statuses can go straight into the DigiKey cart. */
export const ORDERABLE_STATUSES: MatchStatus[] = ['ok', 'marketplace'];

export interface Alternative {
  mpn: string;
  manufacturer: string;
  description: string;
  dkpn: string;
  packaging: string;
  stock: number;
  moq: number;
  unit_price: number | null;
  status: MatchStatus;
  orderable: boolean;
  source: string;
  /** Spec comparison with the original part: drop_in is the only verdict safe to use without review. */
  verdict: Verdict;
  detail: string;
  specs: SpecRow[];
  worse_count: number;
  review: boolean;
  url: string;
  photo: string;
  datasheet: string;
}

export type Verdict = 'drop_in' | 'check' | 'worse' | 'different_package' | 'unverified';

export interface SpecRow {
  name: string;
  original: string;
  candidate: string;
  result: 'same' | 'better' | 'worse' | 'unknown';
}

/** Display fields for the matched DigiKey product. */
export interface ProductCard {
  mpn: string;
  manufacturer: string;
  description: string;
  photo: string;
  datasheet: string;
  url: string;
}

export interface BOMItem {
  designators: string;
  mpn: string;
  manufacturer: string;
  description: string;
  qtyPerBoard: number;
  orderQty: number;
  dkpn: string;
  packaging: string;
  stock: string;
  moq: string;
  unitPrice: number | null;
  status: MatchStatus;
  note: string;
  searchUrl: string;
  alternatives: Alternative[];
  card: ProductCard | null;
  rawRow: Record<string, unknown>;
}

export interface ConvertMeta {
  row_count: number;
  mpn_column: string;
  part_number_column: string | null;
  qty_column: string | null;
  designator_column: string | null;
  boards: number;
  statuses: Record<string, number>;
  api_calls: number;
  api_rate_remaining: number | null;
  cards: (ProductCard | null)[];
}

/** Choice per line: index into item.alternatives, ORIGINAL (keep the BOM part) or SKIP (leave the line out). */
export const ORIGINAL = -1;
export const SKIP = -2;
export type Selections = Record<number, number>;
/** Source label of a replacement the user pasted in themselves. */
export const MANUAL_SOURCE = 'your pick';

function text(value: unknown): string {
  return value === undefined || value === null ? '' : String(value).trim();
}

function asNumber(value: unknown, fallback: number): number {
  const parsed = Number.parseFloat(String(value ?? ''));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeRow(
  row: Record<string, unknown>,
  alternatives: Alternative[],
  card: ProductCard | null,
  meta: ConvertMeta,
): BOMItem {
  const dkMpn = text(row['dk_mpn']);
  const price = asNumber(row['dk_unit_price'], Number.NaN);
  return {
    designators: meta.designator_column ? text(row[meta.designator_column]) : '',
    mpn: dkMpn || text(row[meta.mpn_column]),
    manufacturer: text(row['dk_manufacturer']),
    description: text(row['Description'] ?? row['description']),
    qtyPerBoard: asNumber(row['qty_per_board'], 1),
    orderQty: asNumber(row['order_qty'], 1),
    dkpn: text(row['dkpn']),
    packaging: text(row['dk_packaging']),
    stock: text(row['dk_qty_avail']),
    moq: text(row['dk_moq']),
    unitPrice: Number.isFinite(price) ? price : null,
    status: (text(row['match_status']) || 'error') as MatchStatus,
    note: text(row['match_note']),
    searchUrl: text(row['dk_search_url']),
    alternatives,
    card,
    rawRow: row,
  };
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const response = await fetch(`${BACKEND_BASE}/auth/status`);
  if (!response.ok) {
    throw new Error(`Failed to fetch auth status (${response.status}).`);
  }
  return response.json();
}

export async function convertBOMViaBackend(
  file: File,
  boards: number,
): Promise<{ items: BOMItem[]; meta: ConvertMeta }> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('boards', String(boards));

  const response = await fetch(`${BACKEND_BASE}/convert`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Conversion failed (${response.status}).`);
  }

  const payload = await response.json();
  const rows: Record<string, unknown>[] = Array.isArray(payload.rows) ? payload.rows : [];
  const alternatives: Alternative[][] = Array.isArray(payload.alternatives) ? payload.alternatives : [];
  const meta = payload as ConvertMeta;
  const cards = Array.isArray(meta.cards) ? meta.cards : [];
  return { items: rows.map((row, i) => normalizeRow(row, alternatives[i] || [], cards[i] || null, meta)), meta };
}

/** Look up a replacement the user pasted (DigiKey link, DigiKey part number or MPN) for one BOM line. The backend
 * compares it with the line's original part like the automatic suggestions. */
export async function lookupReplacement(query: string, item: BOMItem): Promise<Alternative> {
  const response = await fetch(`${BACKEND_BASE}/lookup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      need: item.orderQty,
      original_mpn: item.card?.mpn || '',
      original_manufacturer: item.card?.manufacturer || '',
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Lookup failed (${response.status}).`);
  }
  return payload as Alternative;
}

/** What will actually be ordered for a line, given the user's choice of alternative. */
export interface ChosenPart {
  dkpn: string;
  mpn: string;
  manufacturer: string;
  packaging: string;
  unitPrice: number | null;
  orderable: boolean;
  substituted: boolean;
  review: boolean;
}

/** Lines that can't be ordered as the BOM specifies; these need an alternative or a decision to skip. */
export function needsDecision(item: BOMItem): boolean {
  return item.status !== 'not_a_part' && !(ORDERABLE_STATUSES.includes(item.status) && item.dkpn);
}

export function chosenPart(item: BOMItem, selection: number | undefined): ChosenPart | null {
  if (item.status === 'not_a_part' || selection === SKIP) return null;
  const alt = selection !== undefined && selection >= 0 ? item.alternatives[selection] : undefined;
  if (alt) {
    return {
      dkpn: alt.dkpn,
      mpn: alt.mpn,
      manufacturer: alt.manufacturer,
      packaging: alt.packaging,
      unitPrice: alt.unit_price,
      orderable: alt.orderable,
      substituted: true,
      review: alt.review,
    };
  }
  return {
    dkpn: item.dkpn,
    mpn: item.mpn,
    manufacturer: item.manufacturer,
    packaging: item.packaging,
    unitPrice: item.unitPrice,
    orderable: ORDERABLE_STATUSES.includes(item.status) && Boolean(item.dkpn),
    substituted: false,
    review: false,
  };
}

/** Lines that still need a decision: can't be ordered as chosen and not skipped. The cart CSV waits for these. */
export function undecidedLines(items: BOMItem[], selections: Selections): number[] {
  return items.flatMap((item, index) => {
    const part = chosenPart(item, selections[index]);
    return part && !part.orderable ? [index] : [];
  });
}

/** For lines that can't be ordered as-is, preselect the best orderable drop-in replacement (if there is one). */
export function defaultSelections(items: BOMItem[]): Selections {
  const selections: Selections = {};
  items.forEach((item, index) => {
    if (!needsDecision(item)) return;
    const pick = item.alternatives.findIndex((alt) => alt.orderable && alt.verdict === 'drop_in');
    if (pick >= 0) selections[index] = pick;
  });
  return selections;
}

export interface CartLine {
  dkpn: string;
  mpn: string;
  quantity: number;
  designators: string;
}

/** DigiKey cart lines: one per DigiKey part number (duplicates merged), only for orderable choices. */
export function cartLines(items: BOMItem[], selections: Selections): CartLine[] {
  const lines = new Map<string, CartLine>();
  items.forEach((item, index) => {
    const part = chosenPart(item, selections[index]);
    if (!part || !part.orderable) return;
    const existing = lines.get(part.dkpn);
    if (existing) {
      existing.quantity += item.orderQty;
      existing.designators = [existing.designators, item.designators].filter(Boolean).join(', ');
    } else {
      lines.set(part.dkpn, { dkpn: part.dkpn, mpn: part.mpn, quantity: item.orderQty, designators: item.designators });
    }
  });
  return [...lines.values()];
}

/** Column names match DigiKey's cart upload fields, so its auto-mapping picks the right field for each column
 * (with only 3 columns it guessed the designators were manufacturer part numbers). */
function cartRows(items: BOMItem[], selections: Selections) {
  return cartLines(items, selections).map((line) => ({
    'Digi-Key Part Number': line.dkpn,
    'Manufacturer Part Number': line.mpn,
    Quantity: line.quantity,
    'Reference Designator': line.designators,
  }));
}

function download(blob: Blob, filename: string) {
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function exportCartCSV(items: BOMItem[], selections: Selections, filename: string) {
  const csv = Papa.unparse(cartRows(items, selections));
  download(new Blob([csv], { type: 'text/csv;charset=utf-8;' }), filename);
}
