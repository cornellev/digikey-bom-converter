# DigiKey BOM Converter

Convert an Altium-exported BOM (Excel/CSV with manufacturer part numbers) into a DigiKey-compatible BOM with mapped DigiKey part numbers, packaging details, stock status, and product links.

---

## Project Structure

```text
digikey-bom-converter/
├─ backend/
│  ├─ server.py                # FastAPI server entrypoint 
│  ├─ auth_service.py          # DigiKey OAuth/token helpers
│  ├─ bom_service.py           # BOM parsing + mapping helpers
│  ├─ digikey_client.py        # DigiKey Product API client + helpers
│  ├─ storage.py               # Runtime cache for OAuth tokens and MPN lookups
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
DIGIKEY_ENVIRONMENT=prod
DIGIKEY_REDIRECT_URI=https://localhost:5000/auth/callback/
DIGIKEY_SCOPE=productsearch offline_access
FRONTEND_AUTH_REDIRECT=http://localhost:5173/
```

`frontend/.env`

```env
VITE_BACKEND_URL=https://localhost:5000
```

Corresponding example env files can be found in `backend/.env.example` and `frontend/.env.example`.

### 2. Create and configure a DigiKey production app

In the [DigiKey Developer Portal](https://developer.digikey.com/):
1. Create a **Production** app.
2. Subscribe the app to **Product Information API v4**.
3. Set callback URL to exactly: `https://localhost:5000/auth/callback/` (include the trailing slash).
4. Copy **Client ID** and **Client Secret** into `backend/.env`.

### 3. Create local HTTPS certs

Windows (PowerShell):

```powershell
winget install FiloSottile.mkcert
mkcert -install
cd backend
mkdir .certs
mkcert -cert-file .certs/localhost-cert.pem -key-file .certs/localhost-key.pem localhost 127.0.0.1 ::1
```

macOS:

```bash
brew install mkcert
mkcert -install
cd backend
mkdir -p .certs
mkcert -cert-file .certs/localhost-cert.pem -key-file .certs/localhost-key.pem localhost 127.0.0.1 ::1
```

Linux (Ubuntu/Debian):

```bash
sudo apt-get update
sudo apt-get install -y libnss3-tools
curl -JLO "https://dl.filippo.io/mkcert/latest?for=linux/amd64"
chmod +x mkcert-v*-linux-amd64
sudo mv mkcert-v*-linux-amd64 /usr/local/bin/mkcert
mkcert -install
cd backend
mkdir -p .certs
mkcert -cert-file .certs/localhost-cert.pem -key-file .certs/localhost-key.pem localhost 127.0.0.1 ::1
```

Why local certs are needed:
- DigiKey production OAuth requires an HTTPS callback URL.
- This project handles callback in the backend (`/auth/callback/`), so the backend must run on HTTPS locally.

### 4. Run backend 

```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 5000 --env-file .env --ssl-keyfile .certs/localhost-key.pem --ssl-certfile .certs/localhost-cert.pem
```

### 5. Run frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend can be accessed at: <http://localhost:5173>

### 6. Authorize once

1. Open the frontend and click `Connect DigiKey`.
2. Sign in and approve DigiKey access.
3. Verify that <https://localhost:5000/auth/status> shows:
   - `configured: true`
   - `has_refresh_token: true`

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
