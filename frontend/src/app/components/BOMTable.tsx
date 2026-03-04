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
                <TableHead className="px-4 py-3 text-xs tracking-[0.14em] uppercase text-[#535a66]">Original Part Number</TableHead>
                <TableHead className="px-4 py-3 text-xs tracking-[0.14em] uppercase text-[#535a66]">Digi-Key Part Number</TableHead>
                <TableHead className="px-4 py-3 text-xs tracking-[0.14em] uppercase text-[#535a66]">Description</TableHead>
                <TableHead className="px-4 py-3 text-xs tracking-[0.14em] uppercase text-[#535a66]">Manufacturer</TableHead>
                <TableHead className="px-4 py-3 text-right text-xs tracking-[0.14em] uppercase text-[#535a66]">Quantity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((item, index) => (
                <TableRow key={index} className="border-b border-black/5 odd:bg-[#fafbfc] even:bg-white">
                  <TableCell className="px-4 py-3 font-mono text-sm text-[#2b3039]">
                    {item.originalPartNumber}
                  </TableCell>
                  <TableCell className="px-4 py-3 font-mono text-sm text-[#c91118]">
                    {item.digiKeyPartNumber}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-[#353b45]">{item.description}</TableCell>
                  <TableCell className="px-4 py-3 text-[#353b45]">{item.manufacturer}</TableCell>
                  <TableCell className="px-4 py-3 text-right text-[#353b45]">{item.quantity}</TableCell>
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
