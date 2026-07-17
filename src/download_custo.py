"""Baixa uma amostra de 2024 de cada um dos 3 datasets candidatos a fonte de custo
de despacho (CMO Semi-Horário, CMO Semanal, CVU das Usinas Térmicas), em Parquet,
e registra em data/raw/MANIFEST.json — mesmo esquema usado para o resto do projeto.

Só amostra de 2024 — não baixa a série completa.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CUSTO_DIR = RAW_DIR / "custo"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"

ARQUIVOS = {
    "cmo_semi_horario_2024.parquet": "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/cmo_tm/CMO_SEMIHORARIO_2024.parquet",
    "cmo_semanal_2024.parquet": "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/cmo_se/CMO_SEMANAL_2024.parquet",
    "cvu_usina_termica_2024.parquet": "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/cvu_usitermica_se/CVU_USINA_TERMICA_2024.parquet",
}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main():
    CUSTO_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}

    for fname, url in ARQUIVOS.items():
        r = requests.get(url, timeout=120)
        conteudo = r.content
        fpath = CUSTO_DIR / fname
        fpath.write_bytes(conteudo)
        digest = sha256_bytes(conteudo)
        size_bytes = len(conteudo)
        downloaded_at = datetime.now(timezone.utc).astimezone().isoformat()
        manifest[f"custo/{fname}"] = {
            "url": url,
            "status": "ok" if r.status_code == 200 else f"http_{r.status_code}",
            "downloaded_at_local": downloaded_at,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "size_bytes": size_bytes,
            "sha256": digest,
            "fonte": "ONS Dados Abertos",
        }
        print(f"[{r.status_code}] {fname}: {size_bytes} bytes, sha256={digest[:16]}...")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"\nManifesto atualizado: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
