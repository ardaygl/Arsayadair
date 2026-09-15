import httpx
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Arsaya Dair - Parsel Sorgu Uygulaması")

# CORS Güvenlik İzinleri
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

# Bellek içi süper hızlı önbellek (Cache)
CACHE = {}

TKGM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://parselsorgu.tkgm.gov.tr/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}

# En kararlı çalışan adres ilk sıraya alındı
CBS_BASE_URLS = [
    "https://cbsservis.tkgm.gov.tr/megsiswebapi.v3/api",
    "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3/api",
    "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3.1/api"
]

async def fetch_tkgm(path: str):
    """TKGM API'sine istek atan, önbellekleyen ve hata durumunda alternatif URL deneyen motor"""
    if path in CACHE:
        return CACHE[path]

    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=8.0) as client:
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

# 1. İller Listesi
@app.get("/api/iller")
async def get_iller():
    if "iller" in CACHE:
        return CACHE["iller"]
        
    url = "https://parselsorgu.tkgm.gov.tr/app/modules/administrativeQuery/data/ilListe.json"
    async with httpx.AsyncClient(verify=False, timeout=8.0) as client:
        try:
            res = await client.get(url, headers=TKGM_HEADERS)
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
            
    # Fallback (Acil durum illeri)
    return [{"id": 34, "ad": "İSTANBUL"}, {"id": 6, "ad": "ANKARA"}, {"id": 35, "ad": "İZMİR"}]

# 2. İlçeler Listesi
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

# 3. Mahalleler Listesi
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
    path = f"parsel/{mahalle_id}/{parsel}" if ada in ("0", "", None) else f"parsel/{mahalle_id}/{ada}/{parsel}"
    return await fetch_tkgm(path)

# 5. Haritada Tıklanan Noktadan Parsel Bulma
@app.get("/api/parsel-nokta/{lat}/{lng}")
async def get_parsel_nokta(lat: float, lng: float):
    for path in [f"parsel/{lat}/{lng}", f"parsel/{lng}/{lat}"]:
        try:
            return await fetch_tkgm(path)
        except Exception:
            continue
    raise HTTPException(status_code=404, detail="Bu noktada parsel bulunamadı.")

# Sayfa Yönlendirmeleri
def find_file(name: str):
    for p in [BASE_DIR / "static" / name, BASE_DIR / name]:
        if p.exists(): return p
    return None

@app.get("/")
@app.get("/sorgu")
@app.get("/sorgu.html")
async def sorgu_page():
    f = find_file("sorgu.html") or find_file("index.html")
    if f:
        return FileResponse(str(f))
    raise HTTPException(status_code=404, detail="HTML dosyası bulunamadı.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)