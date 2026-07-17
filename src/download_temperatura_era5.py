"""Baixa ERA5 (reanálise, temperature_2m) e a previsão day-ahead
(temperature_2m_previous_day1) para as mesmas 5 cidades do relatório 03, jan/2024 a
dez/2025. Salva em data/raw/temperatura/ e registra em data/raw/MANIFEST.json.

ERA5: https://archive-api.open-meteo.com/v1/archive, models=era5 (reanálise pura, não
o blend "best_match").
Previsão: https://previous-runs-api.open-meteo.com/v1/forecast,
hourly=temperature_2m_previous_day1.

Não altera nada em data/raw/ do ONS.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TEMP_DIR = RAW_DIR / "temperatura"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"

ERA5_URL = "https://archive-api.open-meteo.com/v1/archive"
PREVRUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"

CIDADES = {
    "Sao_Paulo": (-23.5505, -46.6333),
    "Rio_de_Janeiro": (-22.9068, -43.1729),
    "Belo_Horizonte": (-19.9167, -43.9345),
    "Brasilia": (-15.7797, -47.9297),
    "Goiania": (-16.6869, -49.2648),
}

START_DATE = "2024-01-01"
END_DATE = "2025-12-31"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def baixar_e_registrar(fname, url, manifest, meta_extra=None):
    r = requests.get(url, timeout=120)
    conteudo = r.content
    fpath = TEMP_DIR / fname
    fpath.write_bytes(conteudo)
    digest = sha256_bytes(conteudo)
    size_bytes = len(conteudo)
    downloaded_at = datetime.now(timezone.utc).astimezone().isoformat()
    entry = {
        "url": url,
        "status": "ok" if r.status_code == 200 else f"http_{r.status_code}",
        "downloaded_at_local": downloaded_at,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "size_bytes": size_bytes,
        "sha256": digest,
    }
    if meta_extra:
        entry.update(meta_extra)
    manifest[f"temperatura/{fname}"] = entry
    print(f"[{r.status_code}] {fname}: {size_bytes} bytes, sha256={digest[:12]}...")
    return r.status_code, conteudo


def main():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}

    print("=== ERA5 (models=era5), temperature_2m, jan/2024-dez/2025 ===")
    for cidade, (lat, lon) in CIDADES.items():
        params = (
            f"latitude={lat}&longitude={lon}&hourly=temperature_2m"
            f"&start_date={START_DATE}&end_date={END_DATE}"
            f"&timezone=America%2FSao_Paulo&models=era5"
        )
        url = f"{ERA5_URL}?{params}"
        fname = f"era5_temperature_2m_{cidade}_2024_2025.json"
        status, conteudo = baixar_e_registrar(fname, url, manifest, {"fonte": "Open-Meteo Historical Weather API (ERA5)"})
        if status == 200:
            j = json.loads(conteudo)
            print(f"  lat_pedida={lat} lon_pedida={lon} -> lat_grade={j['latitude']} lon_grade={j['longitude']} n_horas={len(j['hourly']['time'])}")

    print("\n=== Previsão day-ahead (previous_day1), temperature_2m, jan/2024-dez/2025 ===")
    for cidade, (lat, lon) in CIDADES.items():
        params = (
            f"latitude={lat}&longitude={lon}&hourly=temperature_2m_previous_day1"
            f"&start_date={START_DATE}&end_date={END_DATE}"
            f"&timezone=America%2FSao_Paulo"
        )
        url = f"{PREVRUNS_URL}?{params}"
        fname = f"openmeteo_previous_day1_{cidade}_2024_2025.json"
        status, conteudo = baixar_e_registrar(fname, url, manifest, {"fonte": "Open-Meteo Previous Runs API"})
        if status == 200:
            j = json.loads(conteudo)
            print(f"  lat_pedida={lat} lon_pedida={lon} -> lat_grade={j['latitude']} lon_grade={j['longitude']} n_horas={len(j['hourly']['time'])}")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"\nManifesto atualizado: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
