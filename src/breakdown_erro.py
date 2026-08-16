"""Breakdown de erro por subgrupo (feriado, estação do ano, dia útil vs. fim de
semana) — ESCOPO.md/FACTS.md seção N. NÃO re-treina nada: recomputa das
previsões JÁ SALVAS, reusando coletar_avaliacoes() de src/custo_assimetrico.py
(a mesma fonte de verdade da seção L, um só cálculo, não dois divergentes).

Estação do ano é hemisfério sul (verão = dez/jan/fev, etc.) — o subsistema
avaliado é SE/CO, hemisfério sul. is_feriado/is_fim_de_semana vêm de
data/processed/features_se.parquet (mesmas colunas usadas no pipeline de
features, não recalculadas aqui de novo).
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from custo_assimetrico import COR, coletar_avaliacoes  # noqa: E402
from modelo_naive import PROCESSED_DIR, SanityCheckError, calcular_custo  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
FIG_DIR = RAIZ / "reports" / "figures"

ESTACAO_POR_MES = {
    12: "verão", 1: "verão", 2: "verão",
    3: "outono", 4: "outono", 5: "outono",
    6: "inverno", 7: "inverno", 8: "inverno",
    9: "primavera", 10: "primavera", 11: "primavera",
}


def carregar_subgrupos() -> pd.DataFrame:
    feat = pd.read_parquet(PROCESSED_DIR / "features_se.parquet",
                            columns=["din_instante", "mes", "is_fim_de_semana", "is_feriado"])
    feat["estacao"] = feat["mes"].map(ESTACAO_POR_MES)
    feat["tipo_dia"] = np.where(feat["is_fim_de_semana"], "fim de semana", "dia útil")
    feat["tipo_feriado"] = np.where(feat["is_feriado"], "feriado", "dia normal")
    return feat[["din_instante", "estacao", "tipo_dia", "tipo_feriado"]]


def _metricas_subgrupo(aval_sub: pd.DataFrame, cmo_horario: pd.Series) -> dict:
    incluida = aval_sub[aval_sub["motivo_exclusao"] == "incluida"].copy()
    if len(incluida) == 0:
        return {"n_horas": 0, "mape": None, "custo_total": None}
    mape = float((incluida["erro"].abs() / incluida["real"].abs()).mean() * 100)
    custo = calcular_custo(aval_sub, cmo_horario)
    return {"n_horas": len(incluida), "mape": mape, "custo_total": custo["custo_total"]}


def breakdown_por_criterio(avaliacoes: dict, subgrupos: pd.DataFrame, cmo_horario: pd.Series, coluna: str) -> pd.DataFrame:
    linhas = []
    for nome, avaliacao in avaliacoes.items():
        merged = avaliacao.merge(subgrupos, on="din_instante", how="left")
        for categoria, grupo in merged.groupby(coluna, observed=True):
            m = _metricas_subgrupo(grupo, cmo_horario)
            linhas.append({"modelo": nome, "criterio": coluna, "categoria": categoria, **m})
    return pd.DataFrame(linhas)


def analisar_degradacao(tabela: pd.DataFrame, coluna_valor: str = "mape"):
    print(f"\n=== Onde cada modelo degrada mais ({coluna_valor.upper()}) ===")
    for nome in tabela["modelo"].unique():
        sub = tabela[tabela["modelo"] == nome].dropna(subset=[coluna_valor])
        pior = sub.loc[sub[coluna_valor].idxmax()]
        melhor = sub.loc[sub[coluna_valor].idxmin()]
        print(f"  {nome}: pior em '{pior['categoria']}' ({coluna_valor}={pior[coluna_valor]:.4f}), "
              f"melhor em '{melhor['categoria']}' ({coluna_valor}={melhor[coluna_valor]:.4f})")


def fig_erro_por_estacao(tabela_estacao: pd.DataFrame):
    ordem_estacoes = ["verão", "outono", "inverno", "primavera"]
    modelos = [m for m in ("naive semanal", "SARIMA", "Prophet", "Chronos-2") if m in tabela_estacao["modelo"].unique()]
    x = np.arange(len(ordem_estacoes))
    largura = 0.8 / len(modelos)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, nome in enumerate(modelos):
        sub = tabela_estacao[tabela_estacao["modelo"] == nome].set_index("categoria").reindex(ordem_estacoes)
        pos = x + (i - (len(modelos) - 1) / 2) * largura
        ax.bar(pos, sub["mape"].to_numpy(), width=largura, color=COR[nome], label=nome)

    ax.set_xticks(x)
    ax.set_xticklabels(ordem_estacoes)
    ax.set_ylabel("MAPE (%)")
    ax.set_title("SE/CO — MAPE por estação do ano (hemisfério sul), por modelo")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    out = FIG_DIR / "resultado_9_erro_por_estacao.png"
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    print(f"\nSalvo: {out.relative_to(RAIZ)}")


def calcular_todos() -> dict:
    avaliacoes, cmo_horario = coletar_avaliacoes()
    subgrupos = carregar_subgrupos()

    tabela_feriado = breakdown_por_criterio(avaliacoes, subgrupos, cmo_horario, "tipo_feriado")
    tabela_estacao = breakdown_por_criterio(avaliacoes, subgrupos, cmo_horario, "estacao")
    tabela_dia = breakdown_por_criterio(avaliacoes, subgrupos, cmo_horario, "tipo_dia")

    conferir_consistencia_interna(avaliacoes, tabela_feriado, tabela_estacao, tabela_dia)
    return {"tabela_feriado": tabela_feriado, "tabela_estacao": tabela_estacao, "tabela_dia": tabela_dia}


def conferir_consistencia_interna(avaliacoes: dict, tabela_feriado: pd.DataFrame,
                                   tabela_estacao: pd.DataFrame, tabela_dia: pd.DataFrame):
    """As 3 estratificações particionam o MESMO conjunto de horas 'incluída' de
    cada modelo — a soma de n_horas por modelo tem que bater nas 3, e bater com
    avaliar_modelo's n_incluida. Se não bater, o merge com features_se.parquet
    perdeu ou duplicou linha — PARA em vez de publicar um breakdown errado."""
    print("\n=== CONTROLE: soma de n_horas por modelo bate nas 3 estratificações ===")
    for nome, avaliacao in avaliacoes.items():
        n_incluida_total = int((avaliacao["motivo_exclusao"] == "incluida").sum())
        somas = {
            "feriado": int(tabela_feriado[tabela_feriado["modelo"] == nome]["n_horas"].sum()),
            "estação": int(tabela_estacao[tabela_estacao["modelo"] == nome]["n_horas"].sum()),
            "dia útil/f.semana": int(tabela_dia[tabela_dia["modelo"] == nome]["n_horas"].sum()),
        }
        ok = all(s == n_incluida_total for s in somas.values())
        print(f"  {nome}: n_incluida={n_incluida_total} | {somas} -> {'OK' if ok else 'DIVERGIU'}")
        if not ok:
            raise SanityCheckError(
                f"{nome}: soma de n_horas por subgrupo ({somas}) não bate com n_incluida do modelo "
                f"({n_incluida_total}) — merge com features_se.parquet perdeu ou duplicou linha. PARANDO."
            )
    print("Confirmado: as 3 estratificações particionam exatamente as mesmas horas em todos os modelos.")


def main():
    resultado = calcular_todos()
    tabela_feriado = resultado["tabela_feriado"]
    tabela_estacao = resultado["tabela_estacao"]
    tabela_dia = resultado["tabela_dia"]

    for nome, tabela in [("FERIADO vs. DIA NORMAL", tabela_feriado), ("ESTAÇÃO DO ANO", tabela_estacao),
                          ("DIA ÚTIL vs. FIM DE SEMANA", tabela_dia)]:
        print(f"\n=== {nome} ===")
        with pd.option_context("display.width", 200, "display.max_columns", None):
            print(tabela.round(4).to_string(index=False))
        analisar_degradacao(tabela)

    RAIZ_REPORTS = RAIZ / "reports"
    RAIZ_REPORTS.mkdir(parents=True, exist_ok=True)
    todas = pd.concat([tabela_feriado, tabela_estacao, tabela_dia], ignore_index=True)
    todas.to_csv(RAIZ_REPORTS / "tabela_breakdown_erro.csv", index=False)
    print(f"\nSalvo: reports/tabela_breakdown_erro.csv")

    fig_erro_por_estacao(tabela_estacao)

    print("\n=== Chronos-2 mantém a vantagem em todos os cortes? ===")
    for nome_tabela, tabela in [("feriado", tabela_feriado), ("estação", tabela_estacao), ("dia útil/f.semana", tabela_dia)]:
        for categoria in tabela["categoria"].unique():
            sub = tabela[tabela["categoria"] == categoria].dropna(subset=["mape"])
            if len(sub) < 2:
                continue
            vencedor = sub.loc[sub["mape"].idxmin(), "modelo"]
            if vencedor != "Chronos-2":
                print(f"  ATENÇÃO: em {nome_tabela}='{categoria}', {vencedor} tem MAPE menor que Chronos-2.")
    print("  (nenhuma linha acima = Chronos-2 vence por MAPE em todos os subgrupos testados)")


if __name__ == "__main__":
    main()
