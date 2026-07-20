"""Baixa CMO Semi-Horário 2025 e 2026 do ONS (mesma fonte/formato da amostra 2024 já
em data/raw/custo/ — src/download_custo.py), completando a cobertura necessária para
avaliar custo sobre todo o período de avaliação (2024-01-01 até o fim da série).

Não re-baixa se o arquivo já existir localmente e o hash bater com o manifesto —
mesmo padrão de src/download_raw.py.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

URL_TEMPLATE = "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/cmo_tm/CMO_SEMIHORARIO_{ano}.parquet"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CUSTO_DIR = RAW_DIR / "custo"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"
ANOS = [2025, 2026]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(manifest: dict) -> None:
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, sort_keys=True)


def main():
    CUSTO_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    for ano in ANOS:
        url = URL_TEMPLATE.format(ano=ano)
        fname = f"cmo_semi_horario_{ano}.parquet"
        chave_manifest = f"custo/{fname}"
        fpath = CUSTO_DIR / fname

        entry = manifest.get(chave_manifest)
        if fpath.exists() and entry is not None:
            local_hash = sha256_of(fpath)
            if local_hash == entry.get("sha256"):
                print(f"[SKIP] {chave_manifest} já existe e hash confere ({local_hash[:12]}...)")
                continue
            else:
                print(f"[REDOWNLOAD] {chave_manifest} existe mas hash diverge do manifesto")

        print(f"[GET] {url}")
        try:
            resp = requests.get(url, timeout=120)
        except requests.RequestException as e:
            print(f"[ERRO] {fname}: falha de rede: {e}")
            manifest[chave_manifest] = {
                "url": url,
                "status": "erro_rede",
                "erro": str(e),
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            save_manifest(manifest)
            continue

        if resp.status_code == 404:
            print(f"[404] {fname} não existe no servidor")
            manifest[chave_manifest] = {
                "url": url,
                "status": "nao_encontrado_404",
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            save_manifest(manifest)
            continue
        elif resp.status_code != 200:
            print(f"[HTTP {resp.status_code}] {fname}")
            manifest[chave_manifest] = {
                "url": url,
                "status": f"http_{resp.status_code}",
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            save_manifest(manifest)
            continue

        fpath.write_bytes(resp.content)
        digest = sha256_of(fpath)
        size_bytes = fpath.stat().st_size
        downloaded_at = datetime.now(timezone.utc).astimezone().isoformat()

        manifest[chave_manifest] = {
            "url": url,
            "status": "ok",
            "downloaded_at_local": downloaded_at,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "size_bytes": size_bytes,
            "sha256": digest,
            "http_last_modified": resp.headers.get("Last-Modified"),
            "http_etag": resp.headers.get("ETag"),
            "fonte": "ONS Dados Abertos",
        }
        print(f"[OK] {fname}: {size_bytes} bytes, sha256={digest[:12]}...")
        save_manifest(manifest)

    print(f"\nManifesto salvo em {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
