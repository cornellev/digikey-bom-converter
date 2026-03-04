# DigiKey BOM Converter 

Convert an Altium-exported BOM (Excel/CSV with manufacturer part numbers) into a DigiKey-compatible BOM with mapped DigiKey part numbers, packaging details, stock status, and product links.

## Quick Start (Local Development)

1. Run Backend: TBD 
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

2. Run Frontend: 

```bash
cd frontend
npm install
npm run dev
```