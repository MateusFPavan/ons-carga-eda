"""Download versionado dos arquivos Parquet de Curva de Carga Horária do ONS.

Baixa cada ano solicitado para data/raw/, registra proveniência (URL, timestamp
com timezone, tamanho em bytes, SHA-256) em data/raw/MANIFEST.json.
Não re-baixa se o arquivo já existir localmente e o hash bater com o manifesto.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

URL_TEMPLATE = "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/curva-carga-ho/CURVA_CARGA_{ano}.parquet"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"
ANOS = list(range(2015, 2027))


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
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    for ano in ANOS:
        url = URL_TEMPLATE.format(ano=ano)
        fname = f"CURVA_CARGA_{ano}.parquet"
        fpath = RAW_DIR / fname

        entry = manifest.get(fname)
        if fpath.exists() and entry is not None:
            local_hash = sha256_of(fpath)
            if local_hash == entry.get("sha256"):
                print(f"[SKIP] {fname} já existe e hash confere ({local_hash[:12]}...)")
                continue
            else:
                print(f"[REDOWNLOAD] {fname} existe mas hash diverge do manifesto")

        print(f"[GET] {url}")
        try:
            resp = requests.get(url, timeout=120)
        except requests.RequestException as e:
            print(f"[ERRO] {fname}: falha de rede: {e}")
            manifest[fname] = {
                "url": url,
                "status": "erro_rede",
                "erro": str(e),
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            continue

        if resp.status_code == 404:
            print(f"[404] {fname} não existe no servidor (ano fora do range publicado)")
            manifest[fname] = {
                "url": url,
                "status": "nao_encontrado_404",
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            continue
        elif resp.status_code != 200:
            print(f"[HTTP {resp.status_code}] {fname}")
            manifest[fname] = {
                "url": url,
                "status": f"http_{resp.status_code}",
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            continue

        fpath.write_bytes(resp.content)
        digest = sha256_of(fpath)
        size_bytes = fpath.stat().st_size
        downloaded_at = datetime.now(timezone.utc).astimezone().isoformat()

        manifest[fname] = {
            "url": url,
            "status": "ok",
            "downloaded_at_local": downloaded_at,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "size_bytes": size_bytes,
            "sha256": digest,
            "http_last_modified": resp.headers.get("Last-Modified"),
            "http_etag": resp.headers.get("ETag"),
        }
        print(f"[OK] {fname}: {size_bytes} bytes, sha256={digest[:12]}...")

        save_manifest(manifest)

    save_manifest(manifest)
    print("Manifesto salvo em", MANIFEST_PATH)


if __name__ == "__main__":
    main()
