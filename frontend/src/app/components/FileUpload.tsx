import { useState, useCallback } from 'react';
import { Upload, FileSpreadsheet } from 'lucide-react';
import { Button } from './ui/button';

interface FileUploadProps {
  onFileSelect: (file: File) => void;
}

export function FileUpload({ onFileSelect }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith('.xlsx') || file.name.endsWith('.xls') || file.name.endsWith('.csv'))) {
      setSelectedFile(file);
      onFileSelect(file);
    }
  }, [onFileSelect]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      onFileSelect(file);
    }
  }, [onFileSelect]);

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`
          group relative overflow-hidden rounded-2xl border-2 border-dashed p-10 text-center transition-all md:p-12
          ${isDragging ? 'border-[#c91118] bg-[#fceff0]' : 'border-[#bfc3cb] bg-[#f8f8fa] hover:border-[#5a606c]'}
        `}
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-[#c91118]/10 to-transparent" />

        <div className="flex flex-col items-center gap-4">
          {selectedFile ? (
            <>
              <FileSpreadsheet className="h-16 w-16 text-[#c91118]" />
              <div className="space-y-2">
                <p className="text-lg text-[#1e222b]">{selectedFile.name}</p>
                <p className="text-sm text-[#4e5561]">
                  {(selectedFile.size / 1024).toFixed(2)} KB
                </p>
              </div>
            </>
          ) : (
            <>
              <Upload className="h-16 w-16 text-[#5f6673] transition-transform duration-300 group-hover:-translate-y-1" />
              <div className="space-y-2">
                <p className="text-lg text-[#1e222b]">
                  Drag and drop your BOM file here
                </p>
                <p className="text-sm text-[#4e5561]">
                  Supports Excel (.xlsx, .xls) and CSV files
                </p>
              </div>
            </>
          )}

          <div className="relative">
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={handleFileInput}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
            <Button variant="outline" className="rounded-full border-black/20 bg-white px-5 text-[#242932] hover:bg-[#efeff2]">
              {selectedFile ? 'Choose Different File' : 'Browse Files'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
