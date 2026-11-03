# DigiKey BOM Converter

Convert an Altium-exported BOM (Excel/CSV with manufacturer part numbers) into a DigiKey order: mapped DigiKey part numbers for N boards, packaging chosen for the quantity, stock checks, in-stock alternatives for parts that can't be ordered, and a cart-ready CSV.

### Deployed Site: https://cornellev.github.io/digikey-bom-converter/

Deployment: the frontend is built and published to GitHub Pages by `.github/workflows/deploy-frontend.yml` on every push
to `main`; it calls the backend at the `VITE_BACKEND_URL` repository secret. The backend (FastAPI) runs on Render.com,
which spins it down when idle, so the first conversion after a while can take ~a minute to start.

---

## Project Structure

```text
digikey-bom-converter/
├─ backend/
│  ├─ server.py                # FastAPI server entrypoint 
│  ├─ auth_service.py          # DigiKey client-credentials token helpers
│  ├─ bom_service.py           # BOM parsing, column detection, part matching, per-line status
│  ├─ alternatives.py          # In-stock replacements (DigiKey substitutes + parametric search)
│  ├─ digikey_client.py        # DigiKey Product API client, packaging/variation choice
│  ├─ storage.py               # Runtime cache for access tokens and API responses
│  ├─ tests/                   # Unit tests (no DigiKey calls): python -m pytest tests
|  ├─ requirements.txt
|  └─ .env.example
├─ frontend/
|  ├─ src/
|  ├─ package.json
|  └─ .env.example
└─ README.md
```

---

## Quick Start (Local Development)

### 1. Configure environment variables

`backend/.env`

```env
DIGIKEY_CLIENT_ID=your_client_id
DIGIKEY_CLIENT_SECRET=your_client_secret
DIGIKEY_AUTH_MODE=client_credentials
DIGIKEY_ENVIRONMENT=prod
DIGIKEY_SCOPE=productsearch
```

`frontend/.env`

```env
VITE_BACKEND_URL=http://localhost:5000
```

Corresponding example env files can be found in `backend/.env.example` and `frontend/.env.example`.

### 2. Create and configure a DigiKey production app

In the [DigiKey Developer Portal](https://developer.digikey.com/):
1. Create a **Production** app.
2. Subscribe the app to **Product Information API v4**.
3. Copy **Client ID** and **Client Secret** into `backend/.env`.

### 3. Run backend 

```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 5000 --env-file .env
```

### 4. Run frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend can be accessed at: <http://localhost:5173>

---

## How matching works

1. **Columns.** The part number comes from `Name` (Altium 365) or `MPN` / `Manufacturer Part Number` / ...; the
   `Part Number` column ("<Manufacturer> <MPN>, ...") is used as a fallback and for the manufacturer. Quantity comes
   from `Qty` / `Quantity` (or the designator count), designators from `Designator`.
2. **Lookup.** Exact DigiKey product lookup by MPN. If DigiKey reports several manufacturers for that MPN (e.g.
   `1N4148WS`), the BOM's manufacturer picks one. Fiducials / mounting holes without a part number are skipped.
3. **Packaging.** For `order_qty = Qty x boards`: Cut Tape, then Digi-Reel, then a full reel only if the order meets
   its minimum. DigiKey Marketplace (third-party) listings only if nothing else covers the quantity.
4. **Alternatives** for lines that can't be ordered (out of stock, minimum order too high, marketplace-only, not
   found): DigiKey's own substitutes first; for resistors, capacitors and inductors also a parametric search (same
   value, package, tolerance, voltage/dielectric ...). Safe drop-ins are preselected in the UI. Anything marked
   **REVIEW** (different package, looser tolerance, non-identical IC/transistor) is never preselected.

DigiKey allows ~1000 API calls/day for the app; a 30-line BOM takes ~60 calls (fewer when cached for 1 h).

## Schema/File Notes

Columns appended to the converted BOM:
- `dk_mpn`, `dk_manufacturer` - the DigiKey product that was matched
- `dkpn`, `dk_packaging`, `dk_qty_avail`, `dk_moq`, `dk_unit_price` - chosen DigiKey variation for the order quantity
- `qty_per_board`, `order_qty` - BOM quantity and quantity x boards
- `match_status` - `ok`, `marketplace`, `moq`, `low_stock`, `out_of_stock`, `ambiguous`, `not_found`, `not_a_part`, `error`
- `match_note` - why, in words (e.g. lead time, which manufacturer was used)
- `dk_search_url` - DigiKey search link for verification
- in exports: `order_dkpn`, `order_mpn`, `order_manufacturer`, `substituted` - what will actually be ordered after
  choosing alternatives

Downloads:
- `[name]_digikey_cart_xN.csv` - `Digi-Key Part Number, Quantity, Customer Reference`, only orderable lines; upload it
  in the DigiKey cart.
- `[name]_digikey_bom_xN.xlsx` - full BOM + "DigiKey cart" + "Needs attention" sheets; `.csv` - full BOM only.

Uploading a previously converted file works too: the appended columns are dropped and recomputed.

---

## License

Internal project use only. Not affiliated with DigiKey Electronics.
