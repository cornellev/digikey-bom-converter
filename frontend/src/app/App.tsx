import { useEffect, useState } from 'react';
import { FileUpload } from './components/FileUpload';
import { BOMTable, BOMItem } from './components/BOMTable';
import {
  AuthStatus,
  BACKEND_BASE,
  convertBOMViaBackend,
  exportToExcel,
  exportToCSV,
  fetchAuthStatus,
} from './utils/BOMConverter';
import { Button } from './components/ui/button';
import { RefreshCw, AlertCircle, Sparkles } from 'lucide-react';
import { Alert, AlertDescription } from './components/ui/alert';
import logoDark from '../assets/images/fulldark.png';

function App() {
  const [bomData, setBomData] = useState<BOMItem[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);

  const refreshAuthStatus = async () => {
    try {
      const status = await fetchAuthStatus();
      setAuthStatus(status);
    } catch {
      setAuthStatus(null);
      setError(`Could not reach backend. Make sure backend is running on ${BACKEND_BASE}.`);
    } finally {
      setIsCheckingAuth(false);
    }
  };

  useEffect(() => {
    refreshAuthStatus();
  }, []);

  const serviceReady = Boolean(authStatus?.configured && authStatus?.has_refresh_token);
  const exportBaseName = uploadedFile?.name
    ? uploadedFile.name.replace(/\.[^/.]+$/, '')
    : 'converted-bom';

  const handleFileSelect = (file: File) => {
    setUploadedFile(file);
    setBomData([]);
    setError(null);
  };

  const handleConvert = async () => {
    if (!uploadedFile) return;

    if (!authStatus?.configured) {
      setError('Not connected to the DigiKey API: service credentials are not configured yet.');
      return;
    }

    if (!authStatus.has_refresh_token) {
      setError('DigiKey API credentials are configured, but service authorization is not ready.');
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      const convertedData = await convertBOMViaBackend(uploadedFile);
      if (convertedData.length === 0) {
        throw new Error('No data found in the uploaded file.');
      }
      setBomData(convertedData);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to process file.';
      setError(message);
      setBomData([]);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownloadExcel = () => {
    if (bomData.length === 0) return;
    exportToExcel(bomData, `${exportBaseName}_digikey_bom.xlsx`);
  };

  const handleDownloadCSV = () => {
    if (bomData.length === 0) return;
    exportToCSV(bomData, `${exportBaseName}_digikey_bom.csv`);
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
          {!isCheckingAuth && authStatus && !authStatus.configured && (
            <Alert variant="destructive" className="rounded-2xl border-red-300/70 bg-red-50/90">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                Not connected to the DigiKey API: service credentials are not configured yet.
              </AlertDescription>
            </Alert>
          )}

          {!isCheckingAuth && authStatus?.configured && !authStatus.has_refresh_token && (
            <Alert variant="destructive" className="rounded-2xl border-red-300/70 bg-red-50/90">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                DigiKey API service authorization is not ready.
              </AlertDescription>
            </Alert>
          )}

          <section className="rounded-3xl border border-black/10 bg-white/90 p-6 shadow-[0_24px_60px_-34px_rgba(17,20,27,0.52)] backdrop-blur-sm md:p-8">
            <FileUpload onFileSelect={handleFileSelect} />

            {uploadedFile && bomData.length === 0 && (
              <div className="mt-8 flex justify-center">
                <Button
                  onClick={handleConvert}
                  disabled={isProcessing || !serviceReady}
                  size="lg"
                  className="h-11 gap-2 rounded-full bg-[#c91118] px-8 text-sm tracking-wide text-[#fafbfc] hover:bg-[#a50e14]"
                >
                  {isProcessing ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Processing File...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4" />
                      Convert to DigiKey BOM
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

          <section className="grid gap-6 md:grid-cols-2">
            <article className="rounded-2xl border border-black/10 bg-white/80 p-6 shadow-[0_18px_40px_-30px_rgba(15,23,42,0.45)] backdrop-blur-sm">
              <h3 className="mb-4 text-2xl tracking-tight text-[#1c2029]">How to Use:</h3>
              <ol className="list-decimal space-y-2 pl-5 text-[#41464f]">
                <li>Upload your Altium-exported BOM (Excel or CSV file with manufacturer part numbers).</li>
                <li>Click "Convert to DigiKey BOM".</li>
                <li>Review the converted DigiKey BOM in the results table.</li>
                <li>Download the output as an Excel or CSV file.</li>
              </ol>
              <p className="mt-4 text-[#41464f]">
                Exported file name:
                <br />
                <span className="font-mono text-[#1f232b]">[original_file_name]_digikey_bom.(xlsx/csv)</span>
              </p>
            </article>

            <article className="rounded-2xl border border-black/10 bg-white/80 p-6 shadow-[0_18px_40px_-30px_rgba(15,23,42,0.45)] backdrop-blur-sm">
              <h3 className="mb-4 text-2xl tracking-tight text-[#1c2029]">Output Columns:</h3>
              <p className="mb-3 text-[#41464f]">The following columns are appended to your BOM:</p>
              <ul className="list-disc space-y-2 pl-5 text-[#41464f]">
                <li><span className="font-mono text-[#1f232b]">dkpn</span> - DigiKey part number (e.g. <span className="font-mono text-[#1f232b]">311-1445-1-ND</span>)</li>
                <li><span className="font-mono text-[#1f232b]">dk_packaging</span> - Selected packaging (prefers Cut Tape / CT)</li>
                <li><span className="font-mono text-[#1f232b]">dk_qty_avail</span> - Available quantity for that packaging</li>
                <li><span className="font-mono text-[#1f232b]">dk_search_url</span> - DigiKey search link for verification</li>
              </ul>
              <p className="mt-3 text-[#41464f]">
                If an MPN returns multiple possible matches or no usable match, these columns are set to{' '}
                <span className="font-mono text-[#1f232b]">MANUAL CHECK REQUIRED</span>.
              </p>
            </article>
          </section>
        </main>
      </div>
    </div>
  );
}

export default App;
