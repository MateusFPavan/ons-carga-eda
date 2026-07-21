"""Completa a cobertura de temperature_2m_previous_day1 (Open-Meteo Previous Runs
API, sem vazamento) para 2026-02-01 até a data mais recente que a API devolver,
5 cidades — mesmo endpoint, parâmetros e coordenadas já usados nos arquivos
existentes (data/raw/temperatura/*_2024_2025.json, *_jan2026.json — confirmados via
MANIFEST.json, não reinventados). Só muda o intervalo de datas.

Não re-baixa se o arquivo já existir e o hash bater com o manifesto — mesmo padrão
de src/download_raw.py.
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

# mesmas coordenadas de src/download_temperatura_testes.py e do MANIFEST.json
# existente — não reinventadas
CIDADES = {
    "Sao_Paulo": (-23.5505, -46.6333),
    "Rio_de_Janeiro": (-22.9068, -43.1729),
    "Belo_Horizonte": (-19.9167, -43.9345),
    "Brasilia": (-15.7797, -47.9297),
    "Goiania": (-16.6869, -49.2648),
}

START_DATE = "2026-02-01"
END_DATE = "2026-07-15"  # fim do período de avaliação; a API pode devolver menos


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_of(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def main():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}

    for cidade, (lat, lon) in CIDADES.items():
        fname = f"openmeteo_previous_day1_{cidade}_fev_jul2026.json"
        chave = f"temperatura/{fname}"
        fpath = TEMP_DIR / fname
        params = (
            f"latitude={lat}&longitude={lon}&hourly=temperature_2m_previous_day1"
            f"&start_date={START_DATE}&end_date={END_DATE}&timezone=America%2FSao_Paulo"
        )
        url = f"{BASE_URL}?{params}"

        entry = manifest.get(chave)
        if fpath.exists() and entry is not None:
            local_hash = sha256_of(fpath)
            if local_hash == entry.get("sha256"):
                print(f"[SKIP] {chave} já existe e hash confere ({local_hash[:12]}...)")
                continue
            else:
                print(f"[REDOWNLOAD] {chave} existe mas hash diverge do manifesto")

        print(f"[GET] {url}")
        r = requests.get(url, timeout=60)
        conteudo = r.content
        fpath.write_bytes(conteudo)
        digest = sha256_bytes(conteudo)
        size_bytes = len(conteudo)
        downloaded_at = datetime.now(timezone.utc).astimezone().isoformat()

        manifest[chave] = {
            "url": url,
            "status": "ok" if r.status_code == 200 else f"http_{r.status_code}",
            "downloaded_at_local": downloaded_at,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "size_bytes": size_bytes,
            "sha256": digest,
            "fonte": "Open-Meteo Previous Runs API",
        }
        print(f"[{r.status_code}] {fname}: {size_bytes} bytes, sha256={digest[:12]}...")
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    print(f"\nManifesto salvo em {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
