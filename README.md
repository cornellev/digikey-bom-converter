# DigiKey BOM Converter

Convert an Altium-exported BOM (Excel/CSV with manufacturer part numbers) into a DigiKey-compatible BOM with mapped DigiKey part numbers, packaging details, stock status, and product links.

---

## Project Structure

```text
digikey-bom-converter/
├─ backend/
│  ├─ server.py                # FastAPI server entrypoint 
│  ├─ auth_service.py          # DigiKey client-credentials token helpers
│  ├─ bom_service.py           # BOM parsing + mapping helpers
│  ├─ digikey_client.py        # DigiKey Product API client + helpers
│  ├─ storage.py               # Runtime cache for access tokens and MPN lookups
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

The frontend can be accessed at: `http://localhost:5173`

---

## Schema/File Notes

The following output columns are appended to the converted BOM:
- `dkpn` - DigiKey part number (e.g. `311-1445-1-ND`)
- `dk_packaging` - Selected packaging (prefers Cut Tape / CT)
- `dk_qty_avail` - Available quantity for that packaging
- `dk_search_url` - DigiKey search link for verification

Export file names:
- `[original_file_name]_digikey_bom.xlsx`
- `[original_file_name]_digikey_bom.csv`

---

## License

Internal project use only. Not affiliated with DigiKey Electronics.
