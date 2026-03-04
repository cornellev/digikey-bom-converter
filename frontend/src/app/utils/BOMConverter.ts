import * as XLSX from 'xlsx';
import Papa from 'papaparse';
import { BOMItem } from '../components/BOMTable';

// Mock conversion function 
function convertToDigiKeyPartNumber(partNumber: string, manufacturer: string): string {
  // This is a mock conversion. With backend, you would:
  // 1. Call DigiKey API with the manufacturer part number
  // 2. Search for matching parts
  // 3. Return the Digi-Key part number
  
  // For demo purposes, we'll generate a mock DigiKey part number
  const prefix = manufacturer.substring(0, 2).toUpperCase();
  const hash = partNumber.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return `${prefix}${hash}-ND`;
}

export async function parseFile(file: File): Promise<any[]> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (e) => {
      try {
        const data = e.target?.result;
        
        if (file.name.endsWith('.csv')) {
          // Parse CSV
          Papa.parse(data as string, {
            header: true,
            skipEmptyLines: true,
            complete: (results) => {
              resolve(results.data);
            },
            error: (error) => {
              reject(error);
            }
          });
        } else {
          // Parse Excel
          const workbook = XLSX.read(data, { type: 'binary' });
          const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
          const jsonData = XLSX.utils.sheet_to_json(firstSheet);
          resolve(jsonData);
        }
      } catch (error) {
        reject(error);
      }
    };
    
    reader.onerror = () => reject(reader.error);
    
    if (file.name.endsWith('.csv')) {
      reader.readAsText(file);
    } else {
      reader.readAsBinaryString(file);
    }
  });
}

export function convertBOM(rawData: any[]): BOMItem[] {
  return rawData.map((row) => {
    // Try to find common column names (case-insensitive)
    const partNumber = 
      row['Part Number'] || 
      row['PartNumber'] || 
      row['part_number'] || 
      row['MPN'] || 
      row['Manufacturer Part Number'] ||
      row['Part #'] ||
      'UNKNOWN';
    
    const description = 
      row['Description'] || 
      row['description'] || 
      row['Desc'] ||
      row['Item Description'] ||
      'No description';
    
    const quantity = 
      parseInt(row['Quantity'] || row['Qty'] || row['quantity'] || row['qty'] || '1');
    
    const manufacturer = 
      row['Manufacturer'] || 
      row['manufacturer'] || 
      row['Mfr'] ||
      row['Mfg'] ||
      'Generic';

    return {
      originalPartNumber: String(partNumber),
      digiKeyPartNumber: convertToDigiKeyPartNumber(String(partNumber), manufacturer),
      description: String(description),
      quantity: quantity,
      manufacturer: manufacturer
    };
  });
}

export function exportToExcel(data: BOMItem[], filename: string = 'converted-bom.xlsx') {
  // Prepare data for export
  const exportData = data.map(item => ({
    'Original Part Number': item.originalPartNumber,
    'Digi-Key Part Number': item.digiKeyPartNumber,
    'Description': item.description,
    'Manufacturer': item.manufacturer,
    'Quantity': item.quantity
  }));

  // Create workbook and worksheet
  const worksheet = XLSX.utils.json_to_sheet(exportData);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, 'BOM');

  // Set column widths
  worksheet['!cols'] = [
    { wch: 20 }, // Original Part Number
    { wch: 20 }, // Digi-Key Part Number
    { wch: 40 }, // Description
    { wch: 15 }, // Manufacturer
    { wch: 10 }  // Quantity
  ];

  // Generate and download file
  XLSX.writeFile(workbook, filename);
}

export function exportToCSV(data: BOMItem[], filename: string = 'converted-bom.csv') {
  // Prepare data for export
  const exportData = data.map(item => ({
    'Original Part Number': item.originalPartNumber,
    'Digi-Key Part Number': item.digiKeyPartNumber,
    'Description': item.description,
    'Manufacturer': item.manufacturer,
    'Quantity': item.quantity
  }));

  // Convert to CSV
  const csv = Papa.unparse(exportData);
  
  // Create blob and download
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
