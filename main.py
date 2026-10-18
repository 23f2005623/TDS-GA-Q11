import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------- CHANGE THESE TWO ----------
EMAIL = "23f2005623@ds.study.iitm.ac.in"            # the address you are logged in with
EXAM_ORIGIN = "https://exam.sanand.workers.dev"  # e.g. https://exam.example.com (no trailing slash, no path)
# --------------------------------------

ASSIGNED_ORIGIN = "https://app-i3ewxf.example.com"
ALLOWED_ORIGINS = [ASSIGNED_ORIGIN, EXAM_ORIGIN]  # never "*"

LIMIT = 10    # B requests ...
WINDOW = 10   # ... per 10 seconds

app = FastAPI()

# client_id -> timestamps of its recent requests
hits: dict[str, deque] = defaultdict(deque)


# Registration order matters: the FIRST one registered is the INNERMOST,
# the LAST one registered is the OUTERMOST (it sees requests first).

# ---- Middleware 3 (innermost): per-client rate limit ----
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.method == "OPTIONS":  # preflights never count
        return await call_next(request)

    client_id = request.headers.get("x-client-id") or (
        request.client.host if request.client else "anonymous"
    )
    now = time.monotonic()
    q = hits[client_id]

    # forget requests older than the window
    while q and now - q[0] >= WINDOW:
        q.popleft()

    if len(q) >= LIMIT:
        retry_after = max(1, int(WINDOW - (now - q[0])) + 1)
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Too Many Requests",
                "request_id": getattr(request.state, "request_id", None),
            },
            headers={"Retry-After": str(retry_after)},
        )

    q.append(now)
    return await call_next(request)

# ---- Middleware 1 (middle): request context ----
@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response

# ---- Middleware 2 (outermost): CORS ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id", "Content-Type"],
    expose_headers=["X-Request-ID"],  # lets browser JS read this header
)

@app.get("/ping")
async def ping(request: Request):
    return {"email": EMAIL, "request_id": request.state.request_id}
