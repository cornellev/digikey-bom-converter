import { Download } from 'lucide-react';
import { Button } from './ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table';

export interface BOMItem {
  originalPartNumber: string;
  digiKeyPartNumber: string;
  description: string;
  quantity: number;
  manufacturer: string;
  rawRow: Record<string, unknown>;
}

interface BOMTableProps {
  data: BOMItem[];
  onDownloadExcel: () => void;
  onDownloadCSV: () => void;
}

export function BOMTable({ data, onDownloadExcel, onDownloadCSV }: BOMTableProps) {
  if (data.length === 0) {
    return null;
  }
  const columns = Object.keys(data[0].rawRow || {});

  return (
    <div className="w-full space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl tracking-tight text-[#1b1f27]">Converted DigiKey-Compatible BOM:</h2>
        <div className="flex items-center gap-2">
          <Button onClick={onDownloadExcel} className="gap-2 rounded-full bg-[#c91118] px-5 text-white hover:bg-[#a40e14]">
            <Download className="w-4 h-4" />
            Download Excel
          </Button>
          <Button onClick={onDownloadCSV} variant="outline" className="gap-2 rounded-full border-black/20 bg-white px-5 text-[#1f232b] hover:bg-[#efeff2]">
            <Download className="w-4 h-4" />
            Download CSV
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-black/10">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader className="bg-[#eef0f4]">
              <TableRow className="hover:bg-[#eef0f4]">
                <TableHead className="px-4 py-3 text-xs tracking-[0.14em] uppercase text-[#535a66]">
                  Row
                </TableHead>
                {columns.map((column) => (
                  <TableHead key={column} className="px-4 py-3 text-xs tracking-[0.14em] uppercase text-[#535a66]">
                    {column}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((item, index) => (
                <TableRow key={index} className="border-b border-black/5 odd:bg-[#fafbfc] even:bg-white">
                  <TableCell className="px-4 py-3 text-sm text-[#353b45]">
                    {index + 1}
                  </TableCell>
                  {columns.map((column) => (
                    <TableCell key={`${index}-${column}`} className="px-4 py-3 text-sm text-[#353b45]">
                      {String(item.rawRow[column] ?? '')}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="text-right text-sm text-[#535a66]">
        Total Items: {data.length}
      </div>
    </div>
  );
}
