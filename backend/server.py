"""FastAPI server entrypoint."""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from auth_service import get_auth_status
from bom_service import convert_uploaded_bom

app = FastAPI(title='DigiKey BOM Converter Backend', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

"""
allow_origins=[
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'https://localhost:5173',
    'https://127.0.0.1:5173',
    'https://cornellev.github.io/digikey-bom-converter'
],
"""

@app.get('/health')
def health() -> dict:
    return {'ok': True}


@app.get('/auth/status')
def auth_status() -> dict:
    try:
        return get_auth_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/convert')
async def convert(
    file: UploadFile = File(...),
    mpn_col: str | None = Form(default=None),
    sheet: str | None = Form(default=None),
    workers: int = Form(default=4),
) -> dict:
    try:
        payload = await file.read()
        rows, meta = convert_uploaded_bom(
            payload=payload,
            filename=file.filename or '',
            mpn_col=mpn_col,
            sheet=sheet,
            workers=workers,
        )
        return {
            'rows': rows,
            'row_count': meta['row_count'],
            'mpn_column': meta['mpn_column'],
            'sheet': meta['sheet'],
            'workers': meta['workers'],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
