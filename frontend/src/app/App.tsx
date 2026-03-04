import { useState } from 'react';
import { FileUpload } from './components/FileUpload';
import { BOMTable, BOMItem } from './components/BOMTable';
import { parseFile, convertBOM, exportToExcel, exportToCSV } from './utils/BOMConverter';
import { Button } from './components/ui/button';
import { RefreshCw, AlertCircle, Sparkles } from 'lucide-react';
import { Alert, AlertDescription } from './components/ui/alert';
import logoDark from '../assets/images/fulldark.png';

function App() {
  const [bomData, setBomData] = useState<BOMItem[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);

  const handleFileSelect = (file: File) => {
    setUploadedFile(file);
    setBomData([]);
    setError(null);
  };

  const handleConvert = async () => {
    if (!uploadedFile) return;

    setIsProcessing(true);
    setError(null);

    try {
      // Parse the file
      const rawData = await parseFile(uploadedFile);
      
      if (rawData.length === 0) {
        throw new Error('No data found in the uploaded file.');
      }

      // Convert to Digi-Key format
      const convertedData = convertBOM(rawData);
      setBomData(convertedData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process file.');
      setBomData([]);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownloadExcel = () => {
    if (bomData.length === 0) return;
    exportToExcel(bomData);
  };

  const handleDownloadCSV = () => {
    if (bomData.length === 0) return;
    exportToCSV(bomData);
  };

  const handleReset = () => {
    setBomData([]);
    setUploadedFile(null);
    setError(null);
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#f2f2f4_0%,_#ececef_40%,_#e4e5e9_100%)] px-4 py-8 md:px-6 md:py-12">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-20 top-16 h-56 w-56 rounded-full bg-[#c91118]/18 blur-3xl" />
        <div className="absolute right-0 top-0 h-72 w-72 rounded-full bg-[#1f2229]/12 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-6xl space-y-8">
        <header className="rounded-3xl border border-black/10 bg-white/88 p-6 shadow-[0_24px_60px_-34px_rgba(17,20,27,0.55)] backdrop-blur-sm md:p-10">
          <div className="flex items-start justify-between gap-4">
            <img
              src={logoDark}
              alt="Cornell Electric Vehicles logo"
              className="h-14 w-auto md:h-16"
            />
          </div>
          <h1 className="mt-4 text-4xl leading-tight tracking-tight text-[#171a21] md:text-5xl">
            DigiKey BOM Converter
          </h1>
          <p className="mt-3 max-w-2xl text-base text-[#3b3f47] md:text-lg">
            Convert an Altium-exported BOM into a DigiKey-compatible BOM! 
          </p>
        </header>

        <main className="space-y-6">
          <section className="rounded-3xl border border-black/10 bg-white/90 p-6 shadow-[0_24px_60px_-34px_rgba(17,20,27,0.52)] backdrop-blur-sm md:p-8">
            <FileUpload onFileSelect={handleFileSelect} />

            {uploadedFile && bomData.length === 0 && (
              <div className="mt-8 flex justify-center">
                <Button
                  onClick={handleConvert}
                  disabled={isProcessing}
                  size="lg"
                  className="h-11 gap-2 rounded-full bg-[#c91118] px-8 text-sm tracking-wide text-[#fafbfc] hover:bg-[#a50e14]"
                >
                  {isProcessing ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Processing File
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4" />
                      Convert to Digi-Key BOM
                    </>
                  )}
                </Button>
              </div>
            )}
          </section>

          {error && (
            <Alert variant="destructive" className="rounded-2xl border-red-300/70 bg-red-50/90">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {bomData.length > 0 && (
            <section className="rounded-3xl border border-black/10 bg-white/90 p-6 shadow-[0_24px_60px_-34px_rgba(17,20,27,0.52)] md:p-8">
              <BOMTable
                data={bomData}
                onDownloadExcel={handleDownloadExcel}
                onDownloadCSV={handleDownloadCSV}
              />

              <div className="mt-8 flex justify-center">
                <Button
                  onClick={handleReset}
                  variant="outline"
                  className="gap-2 rounded-full border-black/20 bg-[#f8f8fa] px-6 text-[#1f232b] hover:bg-[#efeff2]"
                >
                  <RefreshCw className="w-4 h-4" />
                  Convert Another File
                </Button>
              </div>
            </section>
          )}

          <section>
            <article className="rounded-2xl border border-black/10 bg-white/80 p-6 shadow-[0_18px_40px_-30px_rgba(15,23,42,0.45)] backdrop-blur-sm">
              <h3 className="mb-4 text-2xl tracking-tight text-[#1c2029]">How to Use:</h3>
              <ol className="list-decimal space-y-2 pl-5 text-[#41464f]">
                <li>Upload your Altium-exported BOM (Excel or CSV file with manufacturer part numbers and MPNs).</li>
                <li>Click "Convert to DigiKey BOM".</li>
                <li>Review the converted DigiKey-compatible BOM in the results table.</li>
                <li>Download the output as either an Excel or CSV file.</li>
              </ol>
            </article>
          </section>
        </main>
      </div>
    </div>
  );
}

export default App;
