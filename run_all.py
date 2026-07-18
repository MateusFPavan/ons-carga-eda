"""run_all.py — entry point único de reprodutibilidade do projeto (reports/ESCOPO.md,
seção 15). Ordem fixa: verificar integridade de data/raw/ contra MANIFEST.json ->
gerar_facts -> verificar_facts -> limpar -> gerar_features.

Cada etapa aborta a cadeia inteira se falhar (código de saída != 0 do subprocesso, ou
divergência de hash). Não baixa nada — só verifica o que já está em disco e roda o
pipeline de geração sobre esse dado. Modelagem ainda não existe neste projeto, então
não faz parte desta cadeia.
"""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SRC_DIR = RAIZ / "src"
RAW_DIR = RAIZ / "data" / "raw"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"
PYTHON = sys.executable


class EtapaFalhouError(RuntimeError):
    pass


def sha256_de(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def etapa_verificar_manifest() -> None:
    """Confere sha256 e tamanho de cada arquivo já baixado em data/raw/ contra o
    valor gravado em MANIFEST.json no momento do download. Não baixa nada — só
    detecta se um arquivo em disco foi alterado, corrompido ou removido desde
    então."""
    if not MANIFEST_PATH.exists():
        raise EtapaFalhouError(f"MANIFEST.json ausente: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    divergencias = []
    n_verificados = 0
    for nome_relativo, entrada in manifest.items():
        if entrada.get("status") != "ok":
            continue
        fpath = RAW_DIR / nome_relativo
        if not fpath.exists():
            divergencias.append(f"{nome_relativo}: arquivo ausente em disco")
            continue

        tamanho_esperado = entrada.get("size_bytes")
        tamanho_real = fpath.stat().st_size
        if tamanho_esperado is not None and tamanho_real != tamanho_esperado:
            divergencias.append(f"{nome_relativo}: tamanho diverge (manifest={tamanho_esperado} disco={tamanho_real})")
            continue

        hash_esperado = entrada.get("sha256")
        hash_real = sha256_de(fpath)
        if hash_esperado is None or hash_real != hash_esperado:
            divergencias.append(f"{nome_relativo}: sha256 diverge (manifest={str(hash_esperado)[:12]}... disco={hash_real[:12]}...)")
            continue

        n_verificados += 1

    if divergencias:
        raise EtapaFalhouError(f"{len(divergencias)} divergência(s) de integridade em data/raw/:\n  " + "\n  ".join(divergencias))
    print(f"  {n_verificados} arquivo(s) verificado(s) contra MANIFEST.json — sha256 e tamanho batem em todos.")


def etapa_rodar_script(nome_script: str):
    def rodar() -> None:
        caminho = SRC_DIR / nome_script
        if not caminho.exists():
            raise EtapaFalhouError(f"Script ausente: {caminho}")
        resultado = subprocess.run([PYTHON, str(caminho)], cwd=RAIZ)
        if resultado.returncode != 0:
            raise EtapaFalhouError(f"src/{nome_script} terminou com código de saída {resultado.returncode}.")
    return rodar


ETAPAS = [
    ("Verificar MANIFEST (hashes)", etapa_verificar_manifest),
    ("gerar_facts.py", etapa_rodar_script("gerar_facts.py")),
    ("verificar_facts.py", etapa_rodar_script("verificar_facts.py")),
    ("limpar.py", etapa_rodar_script("limpar.py")),
    ("gerar_features.py", etapa_rodar_script("gerar_features.py")),
]


def main() -> None:
    print("=== run_all.py — pipeline de reprodutibilidade ===")
    tempos = []

    for nome, funcao in ETAPAS:
        print(f"\n--- {nome} ---")
        inicio = time.monotonic()
        try:
            funcao()
        except EtapaFalhouError as e:
            duracao = time.monotonic() - inicio
            print(f"\nFALHOU em '{nome}' após {duracao:.2f}s: {e}", file=sys.stderr)
            print("\n=== CADEIA ABORTADA ===", file=sys.stderr)
            print("\n=== TEMPOS ATÉ A FALHA ===", file=sys.stderr)
            for n, d in tempos:
                print(f"  {n}: {d:.2f}s", file=sys.stderr)
            print(f"  {nome}: {duracao:.2f}s (FALHOU)", file=sys.stderr)
            sys.exit(1)
        duracao = time.monotonic() - inicio
        tempos.append((nome, duracao))
        print(f"--- OK ({duracao:.2f}s) ---")

    print("\n=== RESUMO DE TEMPOS ===")
    for nome, duracao in tempos:
        print(f"  {nome}: {duracao:.2f}s")
    print(f"  TOTAL: {sum(d for _, d in tempos):.2f}s")
    print("\nPipeline completo — todas as etapas passaram.")


if __name__ == "__main__":
    main()
