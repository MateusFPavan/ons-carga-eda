"""B6: baixa (de fato, para disco) as respostas de teste da Open-Meteo Previous Runs API
usadas em B2 e B4, e registra cada uma em data/raw/MANIFEST.json (mesmo esquema usado
para os arquivos do ONS: URL, timestamp com timezone, tamanho em bytes, SHA-256).

Volume pequeno: só as 15 janelas de teste de B2 (5 cidades x 3 meses) + as 3 janelas
de B4 (previous_day2, só São Paulo). Nenhum ano inteiro baixado.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TEMP_DIR = RAW_DIR / "temperatura"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"
BASE_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"

CIDADES = {
    "Sao_Paulo": (-23.5505, -46.6333),
    "Rio_de_Janeiro": (-22.9068, -43.1729),
    "Belo_Horizonte": (-19.9167, -43.9345),
    "Brasilia": (-15.7797, -47.9297),
    "Goiania": (-16.6869, -49.2648),
}
JANELAS_TESTE = [
    ("2021-03-01", "2021-03-31", "mar2021"),
    ("2024-01-01", "2024-01-31", "jan2024"),
    ("2026-01-01", "2026-01-31", "jan2026"),
]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def baixar_e_registrar(fname, url, manifest):
    r = requests.get(url, timeout=60)
    conteudo = r.content
    fpath = TEMP_DIR / fname
    fpath.write_bytes(conteudo)
    digest = sha256_bytes(conteudo)
    size_bytes = len(conteudo)
    downloaded_at = datetime.now(timezone.utc).astimezone().isoformat()
    manifest[f"temperatura/{fname}"] = {
        "url": url,
        "status": "ok" if r.status_code == 200 else f"http_{r.status_code}",
        "downloaded_at_local": downloaded_at,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "size_bytes": size_bytes,
        "sha256": digest,
        "fonte": "Open-Meteo Previous Runs API",
    }
    print(f"[{r.status_code}] {fname}: {size_bytes} bytes, sha256={digest[:12]}...")


def main():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}

    print("=== B2: temperature_2m_previous_day1, 5 cidades x 3 janelas ===")
    for cidade, (lat, lon) in CIDADES.items():
        for start, end, rotulo in JANELAS_TESTE:
            params = f"latitude={lat}&longitude={lon}&hourly=temperature_2m_previous_day1&start_date={start}&end_date={end}&timezone=America%2FSao_Paulo"
            url = f"{BASE_URL}?{params}"
            fname = f"openmeteo_previous_day1_{cidade}_{rotulo}.json"
            baixar_e_registrar(fname, url, manifest)

    print("\n=== B4: temperature_2m_previous_day2, Sao Paulo x 3 janelas ===")
    lat, lon = CIDADES["Sao_Paulo"]
    for start, end, rotulo in JANELAS_TESTE:
        params = f"latitude={lat}&longitude={lon}&hourly=temperature_2m_previous_day2&start_date={start}&end_date={end}&timezone=America%2FSao_Paulo"
        url = f"{BASE_URL}?{params}"
        fname = f"openmeteo_previous_day2_Sao_Paulo_{rotulo}.json"
        baixar_e_registrar(fname, url, manifest)

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"\nManifesto atualizado: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
