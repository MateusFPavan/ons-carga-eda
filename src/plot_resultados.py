"""Visualizações dos RESULTADOS (não da sondagem) — só plotagem de previsões já
salvas em data/processed/. Nenhum modelo é re-rodado aqui; toda métrica é
recalculada das previsões salvas com as MESMAS funções de src/modelo_naive.py
(avaliar_modelo, calcular_custo, carregar_cmo_horario_se) usadas para gerá-las.

Gráficos:
  1. Heroi — carga real vs. previsão do Chronos-2, banda P10-P90 (semana de 2025)
  2. Concentração de custo — curva de Lorenz-like (naive semanal, período de avaliação)
  3. Efeito da temperatura no Chronos-2 — delta de MAPE por hora e por decil de CMO
  4. Três quebras estruturais — série de carga 2015-2026

NÃO gerados aqui (ver stdout ao final): comparação de 4 modelos (MASE/custo) e
calibração — bloqueados por falta de arquivo (previsões principais de Prophet e
Chronos-2 zero-shot no período 2024-01-01+ nunca foram salvas em parquet, só
impressas em stdout nos commits f87138a e 59b8dc4).
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, INICIO_AVALIACAO, avaliar_modelo, calcular_custo,
    calcular_mae_insample_naive1, calcular_mae_insample_naive_sazonal,
    carregar_cmo_horario_se, checar_cobertura_cmo, gerar_origens,
    previsor_naive, rodar_walkforward, verificar_grade_regular,
)

PROCESSED_DIR = RAIZ / "data" / "processed"
FIG_DIR = RAIZ / "reports" / "figures"
DPI = 150

# paleta consistente entre os gráficos de resultado
COR_REAL = "#222222"
COR_NAIVE = "#999999"
COR_SARIMA = "#4C72B0"
COR_PROPHET = "#DD8452"
COR_CHRONOS = "#55A868"
COR_CUSTO = "#C44E52"


def _finalizar(fig, nome_arquivo):
    fig.tight_layout()
    out = FIG_DIR / nome_arquivo
    fig.savefig(out, dpi=DPI, facecolor="white")
    plt.close(fig)
    print(f"Salvo: {out.relative_to(RAIZ)}")


# ---------------------------------------------------------------------------
# FIG 1 — heroi: real vs. Chronos-2, banda P10-P90, semana de 2025
# ---------------------------------------------------------------------------

def fig_heroi():
    fpath = PROCESSED_DIR / "chronos_ctx_controlado_sem_temp.parquet"
    if not fpath.exists():
        print(f"PARADO (fig heroi): arquivo ausente {fpath}")
        return
    df = pd.read_parquet(fpath)

    inicio, fim = "2025-05-05", "2025-05-12"  # 1a semana completa (seg-dom) de maio/2025
    janela = df[(df["din_instante"] >= inicio) & (df["din_instante"] < fim)].sort_values("din_instante")
    if janela["previsto"].isna().any() or len(janela) != 168:
        print(f"AVISO (fig heroi): janela {inicio}..{fim} incompleta (n={len(janela)}, "
              f"nan_previsto={janela['previsto'].isna().sum()}) — usando mesmo assim os pontos válidos.")

    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.fill_between(janela["din_instante"], janela["p10"], janela["p90"],
                     color=COR_CHRONOS, alpha=0.22, label="Chronos-2 — intervalo P10–P90", linewidth=0)
    ax.plot(janela["din_instante"], janela["real"], color=COR_REAL, linewidth=1.8, label="Carga real")
    ax.plot(janela["din_instante"], janela["previsto"], color=COR_CHRONOS, linewidth=1.6,
             linestyle="--", label="Chronos-2 — previsão (mediana)")

    cobertura = ((janela["real"] >= janela["p10"]) & (janela["real"] <= janela["p90"])).mean() * 100
    ax.set_title(
        f"SE/CO — Previsão day-ahead do Chronos-2 vs. carga real (semana de {inicio} a {fim})\n"
        f"contexto até 2048h, sem covariável de temperatura — cobertura P10–P90 nesta semana: {cobertura:.0f}%"
    )
    ax.set_xlabel("Data")
    ax.set_ylabel("Carga (MWh/h)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.legend(loc="upper left")
    ax.grid(alpha=0.25)
    _finalizar(fig, "resultado_1_heroi_chronos_semana_2025.png")


# ---------------------------------------------------------------------------
# FIG 2 — concentração de custo (curva tipo Lorenz), naive semanal como instrumento
# ---------------------------------------------------------------------------

def _avaliacao_naive_periodo_completo():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_AVALIACAO)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()

    mae1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)

    previsto = rodar_walkforward(serie_alvo, origens, previsor_naive(168))
    resultado = avaliar_modelo(df, previsto, mae1, mae_saz)
    return df, resultado, fim_serie


def fig_concentracao_custo():
    df, resultado, fim_serie = _avaliacao_naive_periodo_completo()
    cobertura = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    if not cobertura["completo"]:
        print(f"PARADO (fig concentração de custo): CMO incompleto {cobertura}")
        return
    cmo_horario = carregar_cmo_horario_se(cobertura["anos_presentes"])
    custo = calcular_custo(resultado["avaliacao"], cmo_horario)

    incluida = resultado["avaliacao"][resultado["avaliacao"]["motivo_exclusao"] == "incluida"].copy()
    incluida["cmo"] = incluida["din_instante"].map(cmo_horario)
    base = incluida.dropna(subset=["cmo"]).copy()
    base["custo_hora"] = base["erro"].abs() * base["cmo"]
    base = base.sort_values("cmo", ascending=False).reset_index(drop=True)

    n = len(base)
    frac_horas = (np.arange(1, n + 1)) / n * 100
    frac_custo_acum = base["custo_hora"].cumsum() / base["custo_hora"].sum() * 100

    pct_top10_calc = float(np.interp(10, frac_horas, frac_custo_acum))
    diverge = abs(pct_top10_calc - custo["pct_custo_top10pct_cmo"]) > 0.5
    print(f"Concentração de custo (10% horas mais caras de CMO): {custo['pct_custo_top10pct_cmo']:.4f}% "
          f"(FACTS.md seção K2: 25,2248%) — {'DIVERGE, checar' if diverge else 'bate'}")

    fig, ax = plt.subplots(figsize=(8.5, 7))
    ax.plot(frac_horas, frac_custo_acum, color=COR_CUSTO, linewidth=2.2,
            label="Custo acumulado (instrumento: naive semanal)")
    ax.plot([0, 100], [0, 100], color="#999999", linewidth=1, linestyle=":", label="Distribuição uniforme (referência)")

    y10 = custo["pct_custo_top10pct_cmo"]
    ax.axvline(10, color=COR_REAL, linewidth=0.8, linestyle="--")
    ax.axhline(y10, color=COR_REAL, linewidth=0.8, linestyle="--")
    ax.annotate(f"{y10:.1f}% do custo\nnas 10% horas\nde CMO mais alto",
                xy=(10, y10), xytext=(28, y10 - 12),
                arrowprops=dict(arrowstyle="->", color=COR_REAL), fontsize=10)

    ax.set_title("SE/CO — Concentração do custo do erro de previsão por hora de CMO\n"
                  f"período de avaliação {INICIO_AVALIACAO.date()} a {fim_serie.date()}, instrumento: naive semanal")
    ax.set_xlabel("Fração das horas, ordenadas da mais cara para a mais barata (%)")
    ax.set_ylabel("Fração acumulada do custo total (%)")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.legend(loc="lower right")
    ax.grid(alpha=0.25)
    _finalizar(fig, "resultado_2_concentracao_custo.png")


# ---------------------------------------------------------------------------
# FIG 3 — efeito da temperatura no Chronos-2 (contexto controlado, commit adb309b)
# ---------------------------------------------------------------------------

def fig_efeito_temperatura():
    f_sem = PROCESSED_DIR / "chronos_ctx_controlado_sem_temp.parquet"
    f_com = PROCESSED_DIR / "chronos_ctx_controlado_com_temp.parquet"
    if not f_sem.exists() or not f_com.exists():
        print(f"PARADO (fig efeito temperatura): arquivo ausente entre {f_sem} / {f_com}")
        return
    sem = pd.read_parquet(f_sem)
    com = pd.read_parquet(f_com)

    a = sem[sem["motivo_exclusao"] == "incluida"][["din_instante", "previsto", "real"]].rename(columns={"previsto": "previsto_sem"})
    b = com[com["motivo_exclusao"] == "incluida"][["din_instante", "previsto"]].rename(columns={"previsto": "previsto_com"})
    m = a.merge(b, on="din_instante", how="inner")
    if len(m) == 0:
        print("PARADO (fig efeito temperatura): merge sem/com temperatura vazio.")
        return
    m["mape_sem"] = (m["previsto_sem"] - m["real"]).abs() / m["real"].abs() * 100
    m["mape_com"] = (m["previsto_com"] - m["real"]).abs() / m["real"].abs() * 100
    m["hora"] = m["din_instante"].dt.hour

    delta_agregado = m["mape_com"].mean() - m["mape_sem"].mean()
    print(f"Delta MAPE agregado (com - sem temperatura, contexto controlado): {delta_agregado:+.4f}pp")

    por_hora = m.groupby("hora").apply(
        lambda g: pd.Series({"sem": g["mape_sem"].mean(), "com": g["mape_com"].mean()})
    )
    por_hora["delta"] = por_hora["com"] - por_hora["sem"]

    ano_min, ano_max = int(m["din_instante"].dt.year.min()), int(m["din_instante"].dt.year.max())
    cobertura = checar_cobertura_cmo(ano_min, ano_max)
    por_decil = None
    if cobertura["completo"]:
        cmo_horario = carregar_cmo_horario_se(cobertura["anos_presentes"]).rename("cmo")
        m2 = m.merge(cmo_horario, left_on="din_instante", right_index=True, how="left").dropna(subset=["cmo"])
        m2["decil_cmo"] = pd.qcut(m2["cmo"], 10, labels=False, duplicates="drop")
        por_decil = m2.groupby("decil_cmo").apply(
            lambda g: pd.Series({"sem": g["mape_sem"].mean(), "com": g["mape_com"].mean()})
        )
        por_decil["delta"] = por_decil["com"] - por_decil["sem"]
    else:
        print(f"AVISO (fig efeito temperatura): CMO incompleto para decis {cobertura}")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    cores_hora = ["#2E7D32" if 18 <= h <= 21 else "#B0B0B0" for h in por_hora.index]
    axes[0].bar(por_hora.index, por_hora["delta"], color=cores_hora)
    axes[0].axhline(0, color="#444444", linewidth=0.8)
    axes[0].set_title("Delta de MAPE por hora do dia\n(destaque: 18h-21h, pico de carga)")
    axes[0].set_xlabel("Hora do dia")
    axes[0].set_ylabel("Delta de MAPE — com temp. menos sem temp. (p.p.)")
    axes[0].set_xticks(range(0, 24, 2))
    axes[0].grid(alpha=0.25, axis="y")

    if por_decil is not None:
        cores_decil = plt.get_cmap("YlOrRd")(np.linspace(0.25, 0.9, len(por_decil)))
        axes[1].bar(por_decil.index, por_decil["delta"], color=cores_decil)
        axes[1].axhline(0, color="#444444", linewidth=0.8)
        axes[1].set_title("Delta de MAPE por decil de CMO\n(0 = mais barato, 9 = mais caro)")
        axes[1].set_xlabel("Decil de CMO horário")
        axes[1].set_ylabel("Delta de MAPE — com temp. menos sem temp. (p.p.)")
        axes[1].set_xticks(range(len(por_decil)))
        axes[1].grid(alpha=0.25, axis="y")
    else:
        axes[1].axis("off")
        axes[1].text(0.5, 0.5, "CMO indisponível\npara este recorte", ha="center", va="center")

    fig.suptitle(f"Chronos-2 — efeito da temperatura como covariável (contexto controlado, commit adb309b)\n"
                 f"delta agregado: {delta_agregado:+.4f} p.p. de MAPE (negativo = temperatura melhora a previsão)",
                 fontsize=11)
    _finalizar(fig, "resultado_3_efeito_temperatura_chronos.png")


# ---------------------------------------------------------------------------
# FIG 4 — três quebras estruturais na série de carga
# ---------------------------------------------------------------------------

def fig_quebras_estruturais():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    daily = df.set_index("din_instante")["val_cargaenergiahomwmed"].resample("D").mean()

    fig, ax = plt.subplots(figsize=(14, 5.5))
    ax.plot(daily.index, daily.values, linewidth=0.6, color="#4C72B0")

    quebras = [
        (pd.Timestamp("2019-01-01"), "Fim do horário de\nverão (2019)", 0.92),
        (pd.Timestamp("2020-03-16"), "Início da pandemia\n(mar/2020)", 0.78),
        (pd.Timestamp("2020-01-01"), "Início da cobertura\nde CMO (2020)", 0.64),
    ]
    for x, label, y_rel in quebras:
        ax.axvline(x, color="#C44E52", linewidth=1.1, linestyle="--", alpha=0.85)
        y = daily.min() + y_rel * (daily.max() - daily.min())
        ax.annotate(label, xy=(x, y), xytext=(8, 0), textcoords="offset points",
                    fontsize=9, color="#8C2D3B", va="center")

    ax.set_title("SE/CO — Carga média diária, 2015–2026, com as três quebras estruturais do projeto")
    ax.set_xlabel("Data")
    ax.set_ylabel("Carga média diária (MWh/h)")
    ax.grid(alpha=0.25)
    _finalizar(fig, "resultado_4_quebras_estruturais.png")


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    fig_heroi()
    fig_concentracao_custo()
    fig_efeito_temperatura()
    fig_quebras_estruturais()

    print(
        "\nNÃO GERADOS — bloqueados por falta de dado salvo:\n"
        "  - Comparação de 4 modelos (naive/SARIMA/Prophet/Chronos) em MASE e custo\n"
        "  - Divergência de ranking erro x custo\n"
        "  - Calibração (cobertura empírica vs. nominal) para Prophet e para o Chronos-2 principal\n"
        "  Motivo: as previsões principais de Prophet (ctx=2 anos, 2024-01-01+, commit f87138a) e do\n"
        "  Chronos-2 zero-shot (melhor config, 2024-01-01+, commit 59b8dc4) nunca foram salvas em\n"
        "  data/processed/ — os dois scripts (src/modelo_prophet.py, src/modelo_chronos2.py) só\n"
        "  imprimem o resultado em stdout, não persistem parquet. Único arquivo de Prophet salvo é\n"
        "  prophet_ctx_controlado_sem_temp.parquet, período 2024-01-20+, gerado por um script separado\n"
        "  (não coberto por src/, rodando em paralelo neste momento) para a comparação de temperatura —\n"
        "  não é o Prophet principal e não tem período comparável ao SARIMA/naive."
    )


if __name__ == "__main__":
    main()
