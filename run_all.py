"""run_all.py — entry point único de reprodutibilidade do projeto (reports/ESCOPO.md,
seção 15). Estagios (--stage):

  data      pipeline de dados: verificar MANIFEST -> gerar_facts -> verificar_facts ->
            limpar -> gerar_features. ~40s. Não muda nada aqui.
  results   NÃO treina nada. Lê as previsões já salvas em data/processed/, recalcula
            MAPE/MASE(sazonal)/custo/calibração com as MESMAS funções usadas para
            gerá-las, confere contra os números já comprometidos em ESCOPO.md/
            FACTS.md (aborta se divergir), salva reports/tabela_comparativa.csv e os
            gráficos de reports/figures/ (src/plot_resultados.py). ~1min.
  models    RE-TREINA (naive/SARIMA/Prophet/Chronos-2), sobrescrevendo as previsões
            salvas. ~4h (Prophet domina, ~2h50min). Pede confirmação interativa, ou
            use --yes para pular o prompt.
  all-fast  data + results, em cadeia. DEFAULT — o que um avaliador roda para
            reproduzir o RESULTADO (tabela + gráficos) sem re-treinar nada. ~1-2min.

Cada etapa aborta a cadeia inteira se falhar (código de saída != 0 do subprocesso,
divergência de hash, ou divergência de métrica contra FACTS.md). Os estágios 'data' e
'results' não baixam nem treinam nada — só verificam/recalculam o que já está em
disco. 'models' é a única exceção (re-treina) e por isso exige confirmação.
"""
import argparse
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


# ---------------------------------------------------------------------------
# Etapas por estágio — a lógica de cada script/verificação não muda aqui, só a
# orquestração de quais rodar e em que ordem.
# ---------------------------------------------------------------------------

DATA_ETAPAS = [
    ("Verificar MANIFEST (hashes)", etapa_verificar_manifest),
    ("gerar_facts.py", etapa_rodar_script("gerar_facts.py")),
    ("verificar_facts.py", etapa_rodar_script("verificar_facts.py")),
    ("limpar.py", etapa_rodar_script("limpar.py")),
    ("gerar_features.py", etapa_rodar_script("gerar_features.py")),
]

RESULTS_ETAPAS = [
    ("Tabela comparativa + gráficos (plot_resultados.py)", etapa_rodar_script("plot_resultados.py")),
    ("Custo assimétrico + viés direcional (custo_assimetrico.py)", etapa_rodar_script("custo_assimetrico.py")),
    ("Breakdown de erro por subgrupo (breakdown_erro.py)", etapa_rodar_script("breakdown_erro.py")),
]

# ordem: naive é instantâneo, SARIMA/Chronos são baratos perto do Prophet — rodar
# Prophet por último não muda o tempo total, mas deixa os resultados rápidos
# disponíveis (data/processed/) antes do gargalo.
MODELS_ETAPAS = [
    ("modelo_naive.py (~instante)", etapa_rodar_script("modelo_naive.py")),
    ("modelo_chronos2.py (~6min, config vencedora 120M@2048h)", etapa_rodar_script("modelo_chronos2.py")),
    ("modelo_sarima.py (~80min)", etapa_rodar_script("modelo_sarima.py")),
    ("modelo_prophet.py (~2h50min, dominante)", etapa_rodar_script("modelo_prophet.py")),
]


def rodar_etapas(etapas, titulo: str) -> None:
    print(f"=== run_all.py — {titulo} ===")
    tempos = []

    for nome, funcao in etapas:
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

    print(f"\n=== RESUMO DE TEMPOS — {titulo} ===")
    for nome, duracao in tempos:
        print(f"  {nome}: {duracao:.2f}s")
    print(f"  TOTAL: {sum(d for _, d in tempos):.2f}s")
    print(f"\n{titulo}: todas as etapas passaram.")


def confirmar_models(pular_prompt: bool) -> None:
    print(
        "\n=== ATENÇÃO: --stage models vai RE-TREINAR os modelos, sobrescrevendo as previsões "
        "salvas em data/processed/ ===\n"
        "  modelo_naive.py     ~instante\n"
        "  modelo_chronos2.py  ~6min   (config vencedora, não o sweep de 10 combinações)\n"
        "  modelo_sarima.py    ~80min\n"
        "  modelo_prophet.py   ~2h50min (dominante)\n"
        "  TOTAL ESTIMADO: ~4h\n"
    )
    if pular_prompt:
        print("--yes informado: seguindo sem confirmação interativa.")
        return
    try:
        resposta = input("Confirma rodar --stage models (~4h)? Digite 'sim' para continuar: ").strip().lower()
    except EOFError:
        print("\nERRO: sessão não-interativa (stdin sem entrada) e --yes não foi passado — não vou "
              "disparar ~4h de treino sem confirmação explícita.", file=sys.stderr)
        sys.exit(1)
    if resposta != "sim":
        print("Cancelado pelo usuário.")
        sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="run_all.py",
        description="Entry point de reprodutibilidade do projeto — ver docstring do módulo para detalhes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Custo de cada estágio:\n"
            "  data       ~40s    — pipeline de dados (verificar/limpar/gerar features), não baixa nada\n"
            "  results    ~1min   — recalcula métricas das previsões JÁ SALVAS + gera tabela e gráficos\n"
            "  models     ~4h     — RE-TREINA os 4 modelos (SARIMA ~80min, Prophet ~2h50min, Chronos ~6min)\n"
            "  all-fast   ~1-2min — data + results (DEFAULT). Reproduz o RESULTADO sem re-treinar.\n"
        ),
    )
    parser.add_argument(
        "--stage", choices=["data", "results", "models", "all-fast"], default="all-fast",
        help="Estágio a rodar (default: all-fast).",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Só usado com --stage models: pula a confirmação interativa antes de disparar ~4h de treino.",
    )
    args = parser.parse_args()

    if args.stage == "data":
        rodar_etapas(DATA_ETAPAS, "estágio 'data'")
    elif args.stage == "results":
        rodar_etapas(RESULTS_ETAPAS, "estágio 'results'")
    elif args.stage == "models":
        confirmar_models(args.yes)
        rodar_etapas(MODELS_ETAPAS, "estágio 'models'")
    elif args.stage == "all-fast":
        rodar_etapas(DATA_ETAPAS + RESULTS_ETAPAS, "estágio 'all-fast' (data + results, sem re-treinar)")


if __name__ == "__main__":
    main()
