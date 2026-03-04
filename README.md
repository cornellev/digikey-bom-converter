# DigiKey BOM Converter 

Convert an Altium-exported BOM (Excel/CSV with manufacturer part numbers) into a DigiKey-compatible BOM with mapped DigiKey part numbers, packaging details, stock status, and product links.

## Project Structure

```text
digikey-bom-converter/
├─ backend/
│  ├─ server.py                # FastAPI server entrypoint 
│  ├─ auth_service.py          # DigiKey OAuth/token helpers
│  ├─ bom_service.py           # BOM parsing + mapping helpers
│  ├─ digikey_client.py        # DigiKey Product API client + helpers
│  ├─ storage.py               # Runtime cache for OAuth tokens and MPN lookups
│  ├─ requirements.txt
│  ├─ .gitignore
│  └─ examples/
│     ├─ .env.example
│     └─ digikey_config.example.json
├─ frontend/
│  ├─ src/
│  │  ├─ app/
│  │  │  ├─ App.tsx
│  │  │  ├─ utils/BOMConverter.ts
│  │  │  └─ components/
│  ├─ package.json
│  └─ vite.config.ts
└─ README.md
```

## Local Development

### 1. Run Backend:  

```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8000

uvicorn server:app --reload --port 8000   --ssl-keyfile .certs/localhost-key.pem   --ssl-certfile .certs/localhost-cert.pem
```

HTTPS for DigiKey OAuth redirect validation:

```bash
mkdir -p .certs
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
  -keyout .certs/localhost-key.pem \
  -out .certs/localhost-cert.pem \
  -subj "/CN=localhost"
```

### 2. Run Frontend: 

```bash
cd frontend
npm install
npm run dev
```

## License
Internal project use only. Not affiliated with DigiKey Electronics.
