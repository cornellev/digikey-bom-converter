"""FastAPI server entrypoint."""

from dotenv import load_dotenv
load_dotenv()

import os
import urllib.parse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from auth_service import complete_oauth_callback, get_auth_status, start_oauth
from bom_service import convert_uploaded_bom

app = FastAPI(title='DigiKey BOM Converter Backend', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:5173',
        'http://127.0.0.1:5173',
        'https://localhost:5173',
        'https://127.0.0.1:5173',
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def _frontend_redirect_base() -> str:
    return os.getenv('FRONTEND_AUTH_REDIRECT', 'http://localhost:5173/').strip()


def _with_query(url: str, **params: str) -> str:
    parsed = urllib.parse.urlparse(url)
    merged = dict(urllib.parse.parse_qsl(parsed.query))
    merged.update({k: v for k, v in params.items() if v})
    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urllib.parse.urlencode(merged),
            parsed.fragment,
        )
    )


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
def auth_callback(code: str, state: str, return_json: bool = False):
    try:
        payload = complete_oauth_callback(code=code, state=state)
        if return_json:
            return payload
        return RedirectResponse(
            url=_with_query(_frontend_redirect_base(), auth='success'),
            status_code=302,
        )
    except Exception as exc:
        if return_json:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(
            url=_with_query(_frontend_redirect_base(), auth='error', message=str(exc)),
            status_code=302,
        )


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
