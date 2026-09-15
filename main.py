import httpx
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Parsel Sorgu Uygulaması")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

CACHE = {}

TKGM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://parselsorgu.tkgm.gov.tr/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

CBS_BASE_URLS = [
    "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3.1/api",
    "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3/api",
    "https://cbsservis.tkgm.gov.tr/megsiswebapi.v3/api"
]

async def fetch_tkgm(path: str):
    if path in CACHE:
        return CACHE[path]

    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=12.0) as client:
        for base in CBS_BASE_URLS:
            url = f"{base}/{path}"
            try:
                res = await client.get(url, headers=TKGM_HEADERS)
                if res.status_code == 200:
                    data = res.json()
                    CACHE[path] = data
                    return data
            except Exception:
                continue

    raise HTTPException(status_code=502, detail=f"TKGM verisi alınamadı ({path})")

# 1. İller Listesi (Sınır geometrileriyle)
@app.get("/api/iller")
async def get_iller():
    if "iller" in CACHE:
        return CACHE["iller"]
    url = "https://parselsorgu.tkgm.gov.tr/app/modules/administrativeQuery/data/ilListe.json"
    async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
        try:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://parselsorgu.tkgm.gov.tr/"})
            if res.status_code == 200:
                data = res.json()
                iller = [
                    {
                        "id": f["properties"]["id"], 
                        "ad": f["properties"]["text"],
                        "geometry": f.get("geometry")
                    } 
                    for f in data.get("features", [])
                ]
                iller.sort(key=lambda x: x["ad"])
                CACHE["iller"] = iller
                return iller
        except Exception:
            pass
    return [{"id": 34, "ad": "İSTANBUL"}, {"id": 6, "ad": "ANKARA"}, {"id": 35, "ad": "İZMİR"}]

# 2. İlçeler Listesi (Sınır geometrileriyle)
@app.get("/api/ilceler/{il_id}")
async def get_ilceler(il_id: int):
    data = await fetch_tkgm(f"idariYapi/ilceListe/{il_id}")
    ilceler = [
        {
            "id": f["properties"]["id"], 
            "ad": f["properties"]["text"],
            "geometry": f.get("geometry")
        } 
        for f in data.get("features", [])
    ]
    ilceler.sort(key=lambda x: x["ad"])
    return ilceler

# 3. Mahalleler Listesi (Sınır geometrileriyle)
@app.get("/api/mahalleler/{ilce_id}")
async def get_mahalleler(ilce_id: int):
    data = await fetch_tkgm(f"idariYapi/mahalleListe/{ilce_id}")
    mahalleler = [
        {
            "id": f["properties"]["id"], 
            "ad": f["properties"]["text"],
            "geometry": f.get("geometry")
        } 
        for f in data.get("features", [])
    ]
    mahalleler.sort(key=lambda x: x["ad"])
    return mahalleler

# 4. Ada / Parsel Sorgusu
@app.get("/api/parsel/{mahalle_id}/{ada}/{parsel}")
async def get_parsel(mahalle_id: int, ada: str, parsel: str):
    path = f"parsel/{mahalle_id}/{parsel}" if ada in ("0", "") else f"parsel/{mahalle_id}/{ada}/{parsel}"
    return await fetch_tkgm(path)

# 5. Koordinat ile Nokta Sorgulama
@app.get("/api/parsel-nokta/{lat}/{lng}")
async def get_parsel_nokta(lat: float, lng: float):
    for path in [f"parsel/{lat}/{lng}", f"parsel/{lng}/{lat}"]:
        try:
            return await fetch_tkgm(path)
        except Exception:
            continue
    raise HTTPException(status_code=404, detail="Bu noktada parsel bulunamadı.")

def find_file(name: str):
    for p in [BASE_DIR / "static" / name, BASE_DIR / name]:
        if p.exists(): return p
    return None

@app.get("/")
async def root():
    f = find_file("index.html")
    return FileResponse(str(f)) if f else HTTPException(404)

@app.get("/sorgu")
@app.get("/sorgu.html")
async def sorgu_page():
    f = find_file("sorgu.html")
    return FileResponse(str(f)) if f else HTTPException(404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)