from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.api.v1 import passes, gate, auth, warden, admin, swd

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to DB 
    print("Starting up... Connecting to database")
    yield
    # Shutdown: Disconnect from DB
    print("Shutting down... Disconnecting from database")

app = FastAPI(
    title="Advanced Gatepass System",
    description="Campus Gatepass System Backend API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(passes.router, prefix="/api/v1/passes", tags=["Passes"])
app.include_router(gate.router, prefix="/api/v1/gate", tags=["Gate Operations"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(warden.router, prefix="/api/v1/warden", tags=["Warden"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(swd.router, prefix="/api/v1/mock-swd", tags=["SWD Mock"])

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Gatepass System Backend is running"}
