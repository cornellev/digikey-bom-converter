import { useEffect, useState } from 'react';
import { FileUpload } from './components/FileUpload';
import { BOMTable } from './components/BOMTable';
import {
  AuthStatus,
  BACKEND_BASE,
  BOMItem,
  ConvertMeta,
  Alternative,
  MANUAL_SOURCE,
  ORIGINAL,
  Selections,
  convertBOMViaBackend,
  defaultSelections,
  exportCartCSV,
  fetchAuthStatus,
  undecidedLines,
} from './utils/BOMConverter';
import { Button } from './components/ui/button';
import { RefreshCw, AlertCircle, Sparkles } from 'lucide-react';
import { Alert, AlertDescription } from './components/ui/alert';
import logoDark from '../assets/images/fulldark.png';

function App() {
  const [bomData, setBomData] = useState<BOMItem[]>([]);
  const [meta, setMeta] = useState<ConvertMeta | null>(null);
  const [selections, setSelections] = useState<Selections>({});
  const [boards, setBoards] = useState(1);
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

  const clearResults = () => {
    setBomData([]);
    setMeta(null);
    setSelections({});
  };

  const handleFileSelect = (file: File) => {
    setUploadedFile(file);
    clearResults();
    setError(null);
  };

  const handleBoardsChange = (value: string) => {
    const parsed = Number.parseInt(value, 10);
    setBoards(Number.isFinite(parsed) && parsed > 0 ? Math.min(parsed, 1000) : 1);
    clearResults(); // quantities change which packaging and alternatives are valid, so re-run
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
      const { items, meta: convertMeta } = await convertBOMViaBackend(uploadedFile, boards);
      if (items.length === 0) {
        throw new Error('No data found in the uploaded file.');
      }
      setBomData(items);
      setMeta(convertMeta);
      setSelections(defaultSelections(items));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to process file.';
      setError(message);
      clearResults();
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSelect = (index: number, choice: number) => {
    setSelections((prev) => ({ ...prev, [index]: choice }));
  };

  /** The user's own replacement replaces any earlier one for that line and is selected if it can be ordered. */
  const handleManual = (index: number, alt: Alternative) => {
    const others = bomData[index].alternatives.filter((a) => a.source !== MANUAL_SOURCE);
    const manual = { ...alt, source: MANUAL_SOURCE };
    setBomData((prev) => prev.map((item, i) => (i === index ? { ...item, alternatives: [...others, manual] } : item)));
    // The manual pick is always last, so indices of the other alternatives don't move.
    setSelections((prev) => {
      const current = prev[index] ?? ORIGINAL;
      const keep = current >= others.length ? ORIGINAL : current; // the previous manual pick is gone
      return { ...prev, [index]: manual.orderable ? others.length : keep };
    });
  };

  const handleDownloadCart = () => {
    if (bomData.length === 0 || undecidedLines(bomData, selections).length > 0) return;
    exportCartCSV(bomData, selections, `${exportBaseName}_digikey_cart_x${boards}.csv`);
  };

  const handleReset = () => {
    clearResults();
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

            <div className="mt-6 flex items-center justify-center gap-3 text-[#2b3039]">
              <label htmlFor="boards" className="text-sm">Number of boards</label>
              <input
                id="boards"
                type="number"
                min={1}
                max={1000}
                value={boards}
                onChange={(e) => handleBoardsChange(e.target.value)}
                className="w-24 rounded-full border border-black/20 bg-white px-4 py-1.5 text-center text-sm"
              />
            </div>

            {uploadedFile && bomData.length === 0 && (
              <div className="mt-6 flex justify-center">
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

          {bomData.length > 0 && meta && (
            <section className="rounded-3xl border border-black/10 bg-white/90 p-6 shadow-[0_24px_60px_-34px_rgba(17,20,27,0.52)] md:p-8">
              <BOMTable
                data={bomData}
                meta={meta}
                selections={selections}
                onSelect={handleSelect}
                onManual={handleManual}
                onDownloadCart={handleDownloadCart}
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
                <li>Upload your Altium-exported BOM (Excel or CSV with manufacturer part numbers and quantities).</li>
                <li>Set the number of boards and click "Convert to DigiKey BOM".</li>
                <li>
                  Review "Parts that can't be ordered as specified". Every in-stock candidate is compared spec by spec
                  with the original part (photo, datasheet and DigiKey link included). True drop-ins are picked
                  automatically; for the rest, choose one, paste your own DigiKey link or part number (it gets the
                  same spec check), or skip the line. The cart CSV unlocks once every line is decided.
                </li>
                <li>
                  Download the <span className="font-semibold">DigiKey cart CSV</span> and upload it in the DigiKey
                  cart ("Upload a File"). On the mapping screen, start at row 2 and set Column 4 to{' '}
                  <span className="font-semibold">Reference Designator</span> (DigiKey leaves it on "Skip"). The file
                  only contains lines that can actually be ordered.
                </li>
              </ol>
            </article>

            <article className="rounded-2xl border border-black/10 bg-white/80 p-6 shadow-[0_18px_40px_-30px_rgba(15,23,42,0.45)] backdrop-blur-sm">
              <h3 className="mb-4 text-2xl tracking-tight text-[#1c2029]">Download:</h3>
              <ul className="list-disc space-y-2 pl-5 text-[#41464f]">
                <li>
                  <span className="font-semibold">DigiKey cart CSV</span>: Digi-Key Part Number, Manufacturer Part Number,
                  Quantity (per board × boards), Reference Designator. Only
                  unlocks once every line is ordered or skipped.
                </li>
                <li>
                  Packaging prefers Cut Tape, then Digi-Reel; full reels and DigiKey Marketplace sellers only when
                  nothing else covers the quantity.
                </li>
              </ul>
            </article>
          </section>
        </main>
      </div>
    </div>
  );
}

export default App;
