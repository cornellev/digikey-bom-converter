"""FastAPI server entrypoint."""

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from auth_service import complete_oauth_callback, get_auth_status, start_oauth
from bom_service import convert_uploaded_bom

app = FastAPI(title='DigiKey BOM Converter Backend', version='0.1.0')


# --- Health Route ---
@app.get('/health')
def health() -> dict:
    return {'ok': True}


# --- Auth Routes ---
@app.get('/auth/status')
def auth_status() -> dict:
    try:
        return get_auth_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get('/auth/start')
def auth_start() -> dict:
    try:
        authorize_url = start_oauth()
        return {'authorize_url': authorize_url}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get('/auth/callback')
def auth_callback(code: str, state: str) -> dict:
    try:
        return complete_oauth_callback(code=code, state=state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Convert Route ---
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
