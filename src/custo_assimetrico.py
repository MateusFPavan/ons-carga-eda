"""Custo assimétrico de previsão (ESCOPO.md seção 12f) — subprevisão (previsto <
real, falta energia: reserva rápida, compra emergencial, corte de carga no
extremo) penalizada mais que superprevisão (previsto > real, sobra capacidade já
comprometida: mais barato). Consenso na literatura de previsão de carga.

NÃO re-treina nada: recomputa das previsões JÁ SALVAS em data/processed/
(naive é recalculado ao vivo, ~instantâneo — não precisa de arquivo). Reusa
avaliar_modelo/calcular_custo_assimetrico/calcular_vies_direcional de
src/modelo_naive.py — não reimplementa nada disso.

fator_sub NÃO é cravado: varredura de sensibilidade [1.0, 1.5, 2.0, 3.0]. 1.0 é o
controle — tem que reproduzir bit-a-bit (dentro da tolerância já estabelecida) o
custo simétrico em reports/tabela_comparativa.csv / ALVOS_COMPROMETIDOS de
src/plot_resultados.py. Se não reproduzir, é bug — o script PARA (SanityCheckError)
em vez de publicar um número não reconciliado.

VOLL (Value of Lost Load, ~US$10.000/MWh em mercados como o MISO — ordens de
magnitude acima do CMO típico, dezenas de R$/MWh) NÃO entra no cálculo: aplica-se
só nas horas de corte de carga efetivo, que este dataset não identifica.
Declarado como limitação (ESCOPO.md seção 16), não modelado.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, INICIO_AVALIACAO, PROCESSED_DIR, SanityCheckError, avaliar_modelo,
    calcular_custo_assimetrico, calcular_mae_insample_naive1, calcular_mae_insample_naive_sazonal,
    calcular_vies_direcional, carregar_cmo_horario_se, checar_cobertura_cmo, gerar_origens,
    previsor_naive, rodar_walkforward, verificar_grade_regular,
)
from plot_resultados import ALVOS_COMPROMETIDOS  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
FIG_DIR = RAIZ / "reports" / "figures"
FATORES_SUB = [1.0, 1.5, 2.0, 3.0]
TOLERANCIA_REL_CONTROLE = 0.005  # fator_sub=1.0 vs. custo simétrico já comprometido

ARQUIVOS_MODELO = {
    "SARIMA": "sarima_previsoes_60d.parquet",
    "Prophet": "prophet_previsoes.parquet",
    "Chronos-2": "chronos_previsoes.parquet",
}
COR = {"naive semanal": "#8c8c8c", "SARIMA": "#3b6cb7", "Prophet": "#e08a3c", "Chronos-2": "#3fa85f"}


def _avaliacao_de_parquet(nome: str, fpath: Path, df: pd.DataFrame, mae1: float, mae_saz: float):
    if not fpath.exists():
        print(f"  AVISO: {nome} — arquivo ausente ({fpath}), pulando.")
        return None
    salvo = pd.read_parquet(fpath)
    previsto = salvo[["din_instante", "previsto"]].drop_duplicates("din_instante")
    return avaliar_modelo(df, previsto, mae1, mae_saz)["avaliacao"]


def coletar_avaliacoes() -> dict:
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_AVALIACAO)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()

    mae1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)
    cobertura_cmo = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    if not cobertura_cmo["completo"]:
        raise SanityCheckError(f"CMO incompleto ({cobertura_cmo}) — não dá para calcular custo assimétrico.")
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"])

    print("=== Recalculando naive semanal (régua) ao vivo — não precisa de parquet ===")
    previsto_naive = rodar_walkforward(serie_alvo, origens, previsor_naive(168))
    avaliacoes = {"naive semanal": avaliar_modelo(df, previsto_naive, mae1, mae_saz)["avaliacao"]}

    for nome, fname in ARQUIVOS_MODELO.items():
        print(f"=== Carregando {nome} de data/processed/{fname} ===")
        aval = _avaliacao_de_parquet(nome, PROCESSED_DIR / fname, df, mae1, mae_saz)
        if aval is not None:
            avaliacoes[nome] = aval

    return avaliacoes, cmo_horario


def sensibilidade_custo_assimetrico(avaliacoes: dict, cmo_horario: pd.Series) -> pd.DataFrame:
    linhas = []
    for nome, avaliacao in avaliacoes.items():
        for fator in FATORES_SUB:
            r = calcular_custo_assimetrico(avaliacao, cmo_horario, fator)
            linhas.append({"modelo": nome, "fator_sub": fator, "custo_total": r["custo_total"],
                            "custo_subprevisao": r["custo_subprevisao"], "custo_superprevisao": r["custo_superprevisao"],
                            "n_horas_sub": r["n_horas_sub"], "n_horas_super": r["n_horas_super"]})
    return pd.DataFrame(linhas)


def conferir_controle_fator_1(tabela: pd.DataFrame):
    print("\n=== CONTROLE: fator_sub=1.0 deve reproduzir o custo simétrico já comprometido ===")
    ctrl = tabela[tabela["fator_sub"] == 1.0]
    for _, row in ctrl.iterrows():
        nome = row["modelo"]
        if nome not in ALVOS_COMPROMETIDOS:
            continue
        alvo = ALVOS_COMPROMETIDOS[nome]["custo_total"]
        obtido = row["custo_total"]
        diff_rel = abs(obtido - alvo) / alvo
        ok = diff_rel < TOLERANCIA_REL_CONTROLE
        print(f"  {nome}: obtido=R$ {obtido:,.2f} alvo(simétrico)=R$ {alvo:,.2f} "
              f"diff_rel={diff_rel*100:.4f}% -> {'OK' if ok else 'DIVERGIU'}")
        if not ok:
            raise SanityCheckError(
                f"{nome}: custo_total(fator_sub=1.0)=R$ {obtido:,.2f} diverge do custo simétrico já "
                f"comprometido (R$ {alvo:,.2f}) além de {TOLERANCIA_REL_CONTROLE*100}% — bug no cálculo "
                "assimétrico (deveria reduzir ao simétrico em fator_sub=1.0). PARANDO."
            )
    print("Confirmado: fator_sub=1.0 reproduz o custo simétrico em todos os modelos disponíveis.")


def vies_direcional(avaliacoes: dict, cmo_horario: pd.Series) -> pd.DataFrame:
    linhas = []
    for nome, avaliacao in avaliacoes.items():
        v = calcular_vies_direcional(avaliacao, cmo_horario)
        linhas.append({"modelo": nome, **v})
    return pd.DataFrame(linhas)


def analisar_robustez_ranking(tabela: pd.DataFrame):
    print("\n=== RANKING POR CUSTO, POR FATOR_SUB ===")
    rankings = {}
    for fator in FATORES_SUB:
        sub = tabela[tabela["fator_sub"] == fator].sort_values("custo_total")
        ranking = sub["modelo"].tolist()
        rankings[fator] = ranking
        print(f"  fator_sub={fator}: {ranking}")

    ranking_base = rankings[1.0]
    robusto = all(rankings[f] == ranking_base for f in FATORES_SUB)
    print(f"\nRanking robusto à assimetria (idêntico em todos os fatores testados): {'SIM' if robusto else 'NÃO'}")
    if not robusto:
        for fator in FATORES_SUB[1:]:
            if rankings[fator] != ranking_base:
                print(f"  Muda em fator_sub={fator}: {ranking_base} -> {rankings[fator]}")

    vencedor_base = ranking_base[0]
    vencedor_maior_fator = rankings[FATORES_SUB[-1]][0]
    print(f"\nVencedor em fator_sub=1.0: {vencedor_base}")
    print(f"Vencedor em fator_sub={FATORES_SUB[-1]}: {vencedor_maior_fator}")
    print(f"Chronos-2 continua vencendo sob custo assimétrico: "
          f"{'SIM' if vencedor_maior_fator == 'Chronos-2' else 'NÃO — ' + vencedor_maior_fator + ' assume a liderança'}")
    return {"rankings": rankings, "robusto": robusto, "vencedor_base": vencedor_base, "vencedor_maior_fator": vencedor_maior_fator}


def fig_custo_assimetrico(tabela: pd.DataFrame):
    ordem = [n for n in ("naive semanal", "SARIMA", "Prophet", "Chronos-2") if n in tabela["modelo"].unique()]
    x = np.arange(len(FATORES_SUB))
    largura = 0.8 / len(ordem)

    fig, ax = plt.subplots(figsize=(11, 6))
    for i, nome in enumerate(ordem):
        sub = tabela[tabela["modelo"] == nome].set_index("fator_sub").loc[FATORES_SUB]
        custos_bi = sub["custo_total"].to_numpy() / 1e9
        pos = x + (i - (len(ordem) - 1) / 2) * largura
        ax.bar(pos, custos_bi, width=largura, color=COR[nome], label=nome)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{f:.1f}×" for f in FATORES_SUB])
    ax.set_xlabel("fator_sub — quanto a subprevisão custa em relação à superprevisão")
    ax.set_ylabel("Custo total (R$ bilhões)")
    ax.set_title("SE/CO — Custo assimétrico por modelo, sob sensibilidade de fator_sub\n"
                  "fator_sub=1.0× é o custo simétrico (controle); VOLL não incluído (ver ESCOPO.md §16)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    out = FIG_DIR / "resultado_8_custo_assimetrico.png"
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    print(f"\nSalvo: {out.relative_to(RAIZ)}")


def calcular_todos() -> dict:
    """Ponto de entrada reusável (chamado por src/gerar_facts.py para a seção L de
    FACTS.md, e por main() abaixo para stdout/CSV/gráfico) — uma única fonte de
    verdade para os números do custo assimétrico."""
    avaliacoes, cmo_horario = coletar_avaliacoes()
    tabela_custo = sensibilidade_custo_assimetrico(avaliacoes, cmo_horario)
    conferir_controle_fator_1(tabela_custo)
    tabela_vies = vies_direcional(avaliacoes, cmo_horario)
    robustez = analisar_robustez_ranking(tabela_custo)
    return {"tabela_custo": tabela_custo, "tabela_vies": tabela_vies, "robustez": robustez}


def main():
    resultado = calcular_todos()
    tabela_custo = resultado["tabela_custo"]
    tabela_vies = resultado["tabela_vies"]

    print("\n=== TABELA: modelo x fator_sub -> custo total ===")
    pivot = tabela_custo.pivot(index="modelo", columns="fator_sub", values="custo_total")
    with pd.option_context("display.width", 200, "display.max_columns", None, "display.float_format", "R$ {:,.2f}".format):
        print(pivot)

    print("\n=== TABELA: viés direcional (% do erro absoluto vindo de sub vs. super) ===")
    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(tabela_vies.round(2).to_string(index=False))

    RAIZ_REPORTS = RAIZ / "reports"
    RAIZ_REPORTS.mkdir(parents=True, exist_ok=True)
    tabela_custo.to_csv(RAIZ_REPORTS / "tabela_custo_assimetrico.csv", index=False)
    print(f"\nSalvo: reports/tabela_custo_assimetrico.csv")
    tabela_vies.to_csv(RAIZ_REPORTS / "tabela_vies_direcional.csv", index=False)
    print(f"Salvo: reports/tabela_vies_direcional.csv")

    fig_custo_assimetrico(tabela_custo)

    print("\nNenhum arquivo .md gerado por este script (FACTS.md é atualizado separadamente "
          "por src/gerar_facts.py, que importa calcular_todos() daqui).")


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
