"""
PIVOT Remote Control API Server
---------------------------------
FastAPI-based REST API for triggering PIVOT modules programmatically.

Start with:
  python main.py --api
  python api_server.py          # direct start
  uvicorn api_server:app --host 0.0.0.0 --port 8080

Authentication:
  All /api/v1/* endpoints (except /api/v1/health) require:
    Authorization: Bearer <your-api-key>

Key management:
  Generate a key:  python -c "from api_auth import generate_key, save_key; k=generate_key(); save_key(k); print(k)"
  Store in .env.api as: PIVOT_API_KEY=<key>
  Or set env var: PIVOT_API_KEY=key1,key2,...
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api_auth import validate_key
from modules.config import load as _load_config

_load_config()

app = FastAPI(
    title="PIVOT Remote Control API",
    description="REST API for the Sweden OSINT Tool — educational use only.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

_bearer = HTTPBearer(auto_error=False)

# In-memory job store  {scan_id: {"status": ..., "result": ..., "created": ...}}
_jobs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if credentials is None or not validate_key(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    # person
    name: str = ""
    city: str = ""
    personnummer: str = ""
    # company
    org_nr: str = ""
    # phone
    phone: str = ""
    # domain / harvest
    domain: str = ""
    deep: bool = False
    # email / paste / correlate / watch
    email: str = ""
    target: str = ""
    # social / github
    username: str = ""
    threads: int = Field(10, ge=1, le=50)
    # github
    github_name: str = Field("", alias="github_name")
    # news
    query: str = ""
    # geo
    address: str = ""
    lat: str = ""
    lon: str = ""
    # wayback
    url: str = ""
    limit: int = Field(30, ge=1, le=200)


class ScanResponse(BaseModel):
    scan_id: str
    status: str
    created: str


class JobResult(BaseModel):
    scan_id: str
    status: str
    created: str
    completed: str | None = None
    result: Any = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------

async def _run_job(scan_id: str, module: str, params: dict[str, Any]) -> None:
    import api_helpers as _h
    _jobs[scan_id]["status"] = "running"
    try:
        loop = asyncio.get_event_loop()
        func_map: dict[str, Any] = {
            "person":    lambda: _h.run_person(
                name=params.get("name", ""),
                city=params.get("city", ""),
                personnummer=params.get("personnummer", ""),
            ),
            "company":   lambda: _h.run_company(
                name=params.get("name", ""),
                org_nr=params.get("org_nr", ""),
            ),
            "phone":     lambda: _h.run_phone(params.get("phone", "")),
            "domain":    lambda: _h.run_domain(params.get("domain", "")),
            "email":     lambda: _h.run_email(params.get("email", "")),
            "social":    lambda: _h.run_social(
                username=params.get("username", ""),
                threads=params.get("threads", 10),
            ),
            "news":      lambda: _h.run_news(params.get("query", "")),
            "geo":       lambda: _h.run_geo(
                address=params.get("address", ""),
                lat=params.get("lat", ""),
                lon=params.get("lon", ""),
            ),
            "github":    lambda: _h.run_github(
                username=params.get("username", ""),
                email=params.get("email", ""),
                name=params.get("name", ""),
            ),
            "wayback":   lambda: _h.run_wayback(
                url=params.get("url", ""),
                limit=params.get("limit", 30),
            ),
            "folkbok":   lambda: _h.run_folkbok(
                name=params.get("name", ""),
                city=params.get("city", ""),
                personnummer=params.get("personnummer", ""),
            ),
            "vehicle":   lambda: _h.run_vehicle(params.get("plate", "")),
            "harvest":   lambda: _h.run_harvest(
                domain=params.get("domain", ""),
                deep=params.get("deep", False),
            ),
            "paste":     lambda: _h.run_paste(params.get("target", "")),
            "correlate": lambda: _h.run_correlate(params.get("target", "")),
        }
        fn = func_map.get(module)
        if fn is None:
            raise ValueError(f"Unknown module: {module}")
        result = await loop.run_in_executor(None, fn)
        _jobs[scan_id]["status"] = "completed"
        _jobs[scan_id]["result"] = result
    except Exception as exc:
        _jobs[scan_id]["status"] = "error"
        _jobs[scan_id]["error"] = str(exc)
    finally:
        _jobs[scan_id]["completed"] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

AVAILABLE_MODULES = [
    "person", "company", "phone", "domain", "email",
    "social", "news", "geo", "github", "wayback",
    "folkbok", "vehicle", "harvest", "paste", "correlate",
]


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "PIVOT API"}


@app.get("/api/v1/modules", dependencies=[Depends(require_auth)])
def list_modules():
    return {"modules": AVAILABLE_MODULES}


@app.post("/api/v1/scan/{module}", response_model=ScanResponse, status_code=202)
async def start_scan(
    module: str,
    body: ScanRequest,
    _: str = Depends(require_auth),
):
    if module not in AVAILABLE_MODULES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module}' not found. Available: {AVAILABLE_MODULES}",
        )

    scan_id = str(uuid.uuid4())
    created = datetime.now(timezone.utc).isoformat()
    _jobs[scan_id] = {"status": "queued", "created": created, "result": None, "error": None, "completed": None}

    # Validate required params per module
    _validate_module_params(module, body)

    params = body.model_dump()
    asyncio.create_task(_run_job(scan_id, module, params))

    return ScanResponse(scan_id=scan_id, status="queued", created=created)


@app.get("/api/v1/scans/{scan_id}", response_model=JobResult)
def get_scan(scan_id: str, _: str = Depends(require_auth)):
    job = _jobs.get(scan_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return JobResult(
        scan_id=scan_id,
        status=job["status"],
        created=job["created"],
        completed=job.get("completed"),
        result=job.get("result"),
        error=job.get("error"),
    )


@app.get("/api/v1/scans", dependencies=[Depends(require_auth)])
def list_scans():
    return {
        "scans": [
            {
                "scan_id": sid,
                "status": j["status"],
                "created": j["created"],
                "completed": j.get("completed"),
            }
            for sid, j in _jobs.items()
        ]
    }


@app.post("/api/v1/auth/generate-key", status_code=201)
def generate_api_key(_: str = Depends(require_auth)):
    """Generate a new API key (requires an existing valid key)."""
    from api_auth import generate_key, save_key
    new_key = generate_key()
    save_key(new_key)
    return {"api_key": new_key, "note": "Key saved to .env.api"}


# ---------------------------------------------------------------------------
# Param validation helper
# ---------------------------------------------------------------------------

def _validate_module_params(module: str, body: ScanRequest) -> None:
    errors: dict[str, str] = {
        "person":    "name" if not body.name else "",
        "company":   "name or org_nr" if not body.name and not body.org_nr else "",
        "phone":     "phone" if not body.phone else "",
        "domain":    "domain" if not body.domain else "",
        "email":     "email" if not body.email else "",
        "social":    "username" if not body.username else "",
        "news":      "query" if not body.query else "",
        "geo":       "address or lat+lon" if not body.address and not (body.lat and body.lon) else "",
        "github":    "username, email, or name" if not body.username and not body.email and not body.name else "",
        "wayback":   "url" if not body.url else "",
        "folkbok":   "name" if not body.name else "",
        "vehicle":   "",  # plate handled separately
        "harvest":   "domain" if not body.domain else "",
        "paste":     "target" if not body.target else "",
        "correlate": "target" if not body.target else "",
    }
    missing = errors.get(module, "")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required field(s) for module '{module}': {missing}",
        )


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8080, reload=False)
