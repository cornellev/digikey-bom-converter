import * as XLSX from 'xlsx';
import Papa from 'papaparse';
import { BOMItem } from '../components/BOMTable';

export const BACKEND_BASE = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export interface AuthStatus {
  configured: boolean;
  has_refresh_token: boolean;
}

function asNumber(value: unknown, fallback: number): number {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function pickField(row: Record<string, unknown>, keys: string[], fallback: string): string {
  for (const key of keys) {
    const value = row[key];
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      return String(value);
    }
  }
  return fallback;
}

function normalizeRow(row: Record<string, unknown>): BOMItem {
  const originalPartNumber = pickField(
    row,
    ['MPN', 'mpn', 'Part Number', 'PartNumber', 'part_number', 'Manufacturer Part Number', 'Part #'],
    'UNKNOWN',
  );

  const description = pickField(
    row,
    ['Description', 'description', 'Desc', 'Item Description'],
    'No description',
  );

  const manufacturer = pickField(
    row,
    ['Manufacturer', 'manufacturer', 'Mfr', 'Mfg'],
    'Generic',
  );

  const digiKeyPartNumber = pickField(
    row,
    ['dkpn', 'Digi-Key Part Number', 'digiKeyPartNumber'],
    '',
  );

  const quantity = asNumber(
    row['Quantity'] ?? row['Qty'] ?? row['quantity'] ?? row['qty'],
    1,
  );

  return {
    originalPartNumber,
    digiKeyPartNumber,
    description,
    quantity,
    manufacturer,
  };
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const response = await fetch(`${BACKEND_BASE}/auth/status`);
  if (!response.ok) {
    throw new Error(`Failed to fetch auth status (${response.status}).`);
  }
  return response.json();
}

export async function fetchAuthorizeUrl(): Promise<string> {
  const response = await fetch(`${BACKEND_BASE}/auth/start`);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Failed to start auth (${response.status}).`);
  }
  const payload = await response.json();
  if (!payload.authorize_url) {
    throw new Error('Backend did not return an authorize URL.');
  }
  return payload.authorize_url;
}

export async function convertBOMViaBackend(file: File): Promise<BOMItem[]> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${BACKEND_BASE}/convert`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Conversion failed (${response.status}).`);
  }

  const payload = await response.json();
  const rows = Array.isArray(payload.rows) ? payload.rows : [];
  return rows.map((row: Record<string, unknown>) => normalizeRow(row));
}

export function exportToExcel(data: BOMItem[], filename: string = 'converted-bom.xlsx') {
  const exportData = data.map(item => ({
    'Original Part Number': item.originalPartNumber,
    'Digi-Key Part Number': item.digiKeyPartNumber,
    'Description': item.description,
    'Manufacturer': item.manufacturer,
    'Quantity': item.quantity
  }));

  const worksheet = XLSX.utils.json_to_sheet(exportData);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, 'BOM');

  worksheet['!cols'] = [
    { wch: 20 },
    { wch: 20 },
    { wch: 40 },
    { wch: 15 },
    { wch: 10 }
  ];

  XLSX.writeFile(workbook, filename);
}

export function exportToCSV(data: BOMItem[], filename: string = 'converted-bom.csv') {
  const exportData = data.map(item => ({
    'Original Part Number': item.originalPartNumber,
    'Digi-Key Part Number': item.digiKeyPartNumber,
    'Description': item.description,
    'Manufacturer': item.manufacturer,
    'Quantity': item.quantity
  }));

  const csv = Papa.unparse(exportData);
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);

  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
