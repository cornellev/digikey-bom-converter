import * as XLSX from 'xlsx';
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
  detail: string;
  review: boolean;
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
}

/** Index into item.alternatives, or -1 for the original part. */
export type Selections = Record<number, number>;

function text(value: unknown): string {
  return value === undefined || value === null ? '' : String(value).trim();
}

function asNumber(value: unknown, fallback: number): number {
  const parsed = Number.parseFloat(String(value ?? ''));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeRow(row: Record<string, unknown>, alternatives: Alternative[], meta: ConvertMeta): BOMItem {
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
  return { items: rows.map((row, i) => normalizeRow(row, alternatives[i] || [], meta)), meta };
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

export function chosenPart(item: BOMItem, selection: number | undefined): ChosenPart | null {
  if (item.status === 'not_a_part') return null;
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

/** For lines that can't be ordered as-is, preselect the first orderable alternative that needs no review. */
export function defaultSelections(items: BOMItem[]): Selections {
  const selections: Selections = {};
  items.forEach((item, index) => {
    if (ORDERABLE_STATUSES.includes(item.status)) return;
    const pick = item.alternatives.findIndex((alt) => alt.orderable && !alt.review);
    if (pick >= 0) selections[index] = pick;
  });
  return selections;
}

export interface CartLine {
  dkpn: string;
  quantity: number;
  reference: string;
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
      existing.reference = [existing.reference, item.designators].filter(Boolean).join(', ');
    } else {
      lines.set(part.dkpn, { dkpn: part.dkpn, quantity: item.orderQty, reference: item.designators });
    }
  });
  // DigiKey's customer reference field is short; keep the start of the designator list.
  return [...lines.values()].map((line) => ({ ...line, reference: line.reference.slice(0, 48) }));
}

function cartRows(items: BOMItem[], selections: Selections) {
  return cartLines(items, selections).map((line) => ({
    'Digi-Key Part Number': line.dkpn,
    Quantity: line.quantity,
    'Customer Reference': line.reference,
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

function fullRows(items: BOMItem[], selections: Selections) {
  return items.map((item, index) => {
    const part = chosenPart(item, selections[index]);
    return {
      ...item.rawRow,
      order_dkpn: part?.orderable ? part.dkpn : '',
      order_mpn: part?.orderable ? part.mpn : '',
      order_manufacturer: part?.orderable ? part.manufacturer : '',
      substituted: part?.substituted ? (part.review ? 'yes (needs review)' : 'yes') : '',
    };
  });
}

export function exportToExcel(items: BOMItem[], selections: Selections, filename: string) {
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(fullRows(items, selections)), 'BOM');
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(cartRows(items, selections)), 'DigiKey cart');

  const attention = items.flatMap((item, index) => {
    const part = chosenPart(item, selections[index]);
    if (!part || part.orderable) return [];
    return [{
      Designator: item.designators,
      'Part number': item.mpn,
      Status: item.status,
      Note: item.note,
      'Order qty': item.orderQty,
      'Alternatives (MPN / DigiKey PN / stock)': item.alternatives
        .map((alt) => `${alt.mpn} / ${alt.dkpn} / ${alt.stock}`)
        .join('; '),
      'DigiKey search': item.searchUrl,
    }];
  });
  if (attention.length) {
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(attention), 'Needs attention');
  }
  XLSX.writeFile(workbook, filename);
}

export function exportToCSV(items: BOMItem[], selections: Selections, filename: string) {
  const csv = Papa.unparse(fullRows(items, selections));
  download(new Blob([csv], { type: 'text/csv;charset=utf-8;' }), filename);
}
