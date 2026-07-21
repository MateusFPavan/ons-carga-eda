"""Visualizações dos RESULTADOS (não da sondagem) — só plotagem de previsões já
salvas em data/processed/. Nenhum modelo é re-rodado aqui; toda métrica é
recalculada das previsões salvas com as MESMAS funções de src/modelo_naive.py
(avaliar_modelo, calcular_custo, carregar_cmo_horario_se) usadas para gerá-las.

Gráficos:
  1. Heroi — carga real vs. previsão do Chronos-2, banda P10-P90 (semana de 2025)
  2. Concentração de custo — curva de Lorenz-like (naive semanal, período de avaliação)
  3. Efeito da temperatura no Chronos-2 — delta de MAPE por hora e por decil de CMO
  4. Três quebras estruturais — série de carga 2015-2026
  5. Comparativo 4 modelos — MASE(sazonal) e custo total (naive/SARIMA/Prophet/Chronos-2)
  6. Erro vs. custo — ranking por MASE(sazonal) vs. ranking por custo total
  7. Calibração — cobertura empírica vs. nominal (80%/90%) para Chronos-2/SARIMA/Prophet

Figuras 5-7 dependiam de data/processed/chronos_previsoes.parquet e
data/processed/prophet_previsoes.parquet — as previsões principais de Prophet e
Chronos-2 zero-shot no período 2024-01-01+, nunca salvas até o commit que
acompanha esta atualização (só impressas em stdout nos commits f87138a e
59b8dc4). Cada uma confere os números recalculados contra os já comprometidos em
reports/ESCOPO.md/FACTS.md (ver ALVOS_COMPROMETIDOS) e PARA (SanityCheckError) se
divergir além da tolerância — não gera gráfico com número não reconciliado.
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
    CARGA_SE_PATH, INICIO_AVALIACAO, SanityCheckError, avaliar_modelo, calcular_custo,
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


# ---------------------------------------------------------------------------
# FIGs 5-7 — comparativo de 4 modelos, erro x custo, calibração
# ---------------------------------------------------------------------------

# Números já comprometidos em reports/ESCOPO.md seção 16 (achado confirmado,
# commit f87138a) e nas verificações de reprodutibilidade de
# src/modelo_chronos2.py / src/modelo_prophet.py — usados só para CONFERIR o que
# é recalculado aqui a partir dos parquets, nunca para plotar diretamente
# (nenhum número digitado à mão vai para o gráfico).
ALVOS_COMPROMETIDOS = {
    "naive semanal": {"mase_sazonal": 1.2732, "custo_total": 8.52e9,
                       "tol_mase": 0.01, "tol_custo_rel": 0.01},
    "SARIMA": {"mase_sazonal": 1.3412, "custo_total": 8_403_964_892.57,
               "tol_mase": 0.002, "tol_custo_rel": 0.005},
    "Prophet": {"mase_sazonal": 1.1678, "mape": 4.9985, "custo_total": 7_863_385_780.72,
                "tol_mase": 0.05, "tol_mape": 0.05, "tol_custo_rel": 0.02},
    "Chronos-2": {"mase_sazonal": 0.4363, "mape": 1.8235, "custo_total": 3_006_870_034.31,
                  "tol_mase": 0.002, "tol_mape": 0.002, "tol_custo_rel": 0.002},
}


def _conferir(nome: str, obtido: dict, alvo: dict):
    for chave, tol_chave in (("mase_sazonal", "tol_mase"), ("mape", "tol_mape")):
        if chave in alvo:
            diff = abs(obtido[chave] - alvo[chave])
            ok = diff < alvo[tol_chave]
            print(f"  {nome} — {chave}: obtido={obtido[chave]:.4f} alvo={alvo[chave]} -> {'OK' if ok else 'DIVERGIU'}")
            if not ok:
                raise SanityCheckError(
                    f"{nome}: {chave} obtido ({obtido[chave]:.4f}) diverge do valor já comprometido "
                    f"({alvo[chave]}) além da tolerância ({alvo[tol_chave]}) — PARANDO, não gero gráfico "
                    "com número não reconciliado."
                )
    if "custo_total" in alvo:
        diff_rel = abs(obtido["custo_total"] - alvo["custo_total"]) / alvo["custo_total"]
        ok = diff_rel < alvo["tol_custo_rel"]
        print(f"  {nome} — custo_total: obtido=R$ {obtido['custo_total']:,.2f} "
              f"alvo=R$ {alvo['custo_total']:,.2f} -> {'OK' if ok else 'DIVERGIU'}")
        if not ok:
            raise SanityCheckError(
                f"{nome}: custo_total obtido (R$ {obtido['custo_total']:,.2f}) diverge do valor já "
                f"comprometido (R$ {alvo['custo_total']:,.2f}) além da tolerância relativa "
                f"({alvo['tol_custo_rel']}) — PARANDO, não gero gráfico com número não reconciliado."
            )


def _carregar_resultado_modelo(nome: str, fpath: Path, df, mae1, mae_saz, cmo_horario) -> dict:
    if not fpath.exists():
        raise SanityCheckError(f"{nome}: arquivo ausente {fpath} — previsão principal não foi salva.")
    salvo = pd.read_parquet(fpath)
    previsto = salvo[["din_instante", "previsto"]].drop_duplicates("din_instante")
    resultado = avaliar_modelo(df, previsto, mae1, mae_saz)
    custo = calcular_custo(resultado["avaliacao"], cmo_horario) if cmo_horario is not None else None
    if custo is None:
        raise SanityCheckError(f"{nome}: CMO indisponível — não dá para conferir custo_total.")

    aval = resultado["avaliacao"].merge(
        salvo[["din_instante", "p10", "p90"]].drop_duplicates("din_instante"), on="din_instante", how="left")
    incluida = aval[aval["motivo_exclusao"] == "incluida"]
    cobertura_80 = float(((incluida["real"] >= incluida["p10"]) & (incluida["real"] <= incluida["p90"])).mean())
    cobertura_90 = None
    if "p05" in salvo.columns and "p95" in salvo.columns:
        aval90 = resultado["avaliacao"].merge(
            salvo[["din_instante", "p05", "p95"]].drop_duplicates("din_instante"), on="din_instante", how="left")
        incl90 = aval90[aval90["motivo_exclusao"] == "incluida"]
        cobertura_90 = float(((incl90["real"] >= incl90["p05"]) & (incl90["real"] <= incl90["p95"])).mean())

    return {
        "mape": resultado["mape"], "mase_sazonal": resultado["mase_sazonal"],
        "custo_total": custo["custo_total"], "cobertura_80": cobertura_80, "cobertura_90": cobertura_90,
    }


def _coletar_resultados_4_modelos():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    fim_serie = df["din_instante"].max()

    mae1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)
    cobertura_cmo = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    if not cobertura_cmo["completo"]:
        raise SanityCheckError(f"CMO incompleto ({cobertura_cmo}) — não dá para comparar custo entre modelos.")
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"])

    print("=== Recalculando naive semanal (régua) a partir do histórico (determinístico, sem parquet) ===")
    _, resultado_naive, _ = _avaliacao_naive_periodo_completo()
    custo_naive = calcular_custo(resultado_naive["avaliacao"], cmo_horario)
    resultados = {
        "naive semanal": {
            "mape": resultado_naive["mape"], "mase_sazonal": resultado_naive["mase_sazonal"],
            "custo_total": custo_naive["custo_total"], "cobertura_80": None, "cobertura_90": None,
        }
    }

    print("=== Carregando SARIMA de data/processed/sarima_previsoes_60d.parquet ===")
    resultados["SARIMA"] = _carregar_resultado_modelo(
        "SARIMA", PROCESSED_DIR / "sarima_previsoes_60d.parquet", df, mae1, mae_saz, cmo_horario)

    print("=== Carregando Prophet de data/processed/prophet_previsoes.parquet ===")
    resultados["Prophet"] = _carregar_resultado_modelo(
        "Prophet", PROCESSED_DIR / "prophet_previsoes.parquet", df, mae1, mae_saz, cmo_horario)

    print("=== Carregando Chronos-2 de data/processed/chronos_previsoes.parquet ===")
    resultados["Chronos-2"] = _carregar_resultado_modelo(
        "Chronos-2", PROCESSED_DIR / "chronos_previsoes.parquet", df, mae1, mae_saz, cmo_horario)

    print("\n=== Conferindo os 4 modelos contra os números já comprometidos (ESCOPO.md/FACTS.md) ===")
    for nome, obtido in resultados.items():
        _conferir(nome, obtido, ALVOS_COMPROMETIDOS[nome])
    print("Confirmado: os 4 modelos batem com os números já documentados. Reprodutibilidade OK.\n")

    return resultados


def fig_comparativo_4_modelos(resultados: dict):
    ordem = ["naive semanal", "SARIMA", "Prophet", "Chronos-2"]
    cores = {"naive semanal": COR_NAIVE, "SARIMA": COR_SARIMA, "Prophet": COR_PROPHET, "Chronos-2": COR_CHRONOS}

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))

    mases = [resultados[n]["mase_sazonal"] for n in ordem]
    axes[0].bar(ordem, mases, color=[cores[n] for n in ordem])
    for i, v in enumerate(mases):
        axes[0].text(i, v, f"{v:.4f}", ha="center", va="bottom", fontsize=9)
    axes[0].axhline(1.0, color="#444444", linewidth=0.8, linestyle=":")
    axes[0].set_title("MASE (denom. sazonal, lag=168h)\nmenor é melhor")
    axes[0].set_ylabel("MASE (sazonal)")
    axes[0].grid(alpha=0.25, axis="y")
    axes[0].tick_params(axis="x", rotation=15)

    custos_bi = [resultados[n]["custo_total"] / 1e9 for n in ordem]
    axes[1].bar(ordem, custos_bi, color=[cores[n] for n in ordem])
    for i, v in enumerate(custos_bi):
        axes[1].text(i, v, f"R$ {v:.2f}bi", ha="center", va="bottom", fontsize=9)
    axes[1].set_title("Custo total do erro de previsão\n(|erro| x CMO horário), menor é melhor")
    axes[1].set_ylabel("Custo total (R$ bilhões)")
    axes[1].grid(alpha=0.25, axis="y")
    axes[1].tick_params(axis="x", rotation=15)

    fig.suptitle(f"SE/CO — Comparativo dos 4 modelos, período de avaliação {INICIO_AVALIACAO.date()}+", fontsize=12)
    _finalizar(fig, "resultado_5_comparativo_4_modelos.png")


def fig_erro_vs_custo(resultados: dict):
    ordem = ["naive semanal", "SARIMA", "Prophet", "Chronos-2"]
    cores = {"naive semanal": COR_NAIVE, "SARIMA": COR_SARIMA, "Prophet": COR_PROPHET, "Chronos-2": COR_CHRONOS}

    ranking_mase = sorted(ordem, key=lambda n: resultados[n]["mase_sazonal"])
    ranking_custo = sorted(ordem, key=lambda n: resultados[n]["custo_total"])
    print(f"Ranking por MASE (melhor->pior): {ranking_mase}")
    print(f"Ranking por custo (melhor->pior): {ranking_custo}")
    print(f"Rankings coincidem: {'sim' if ranking_mase == ranking_custo else 'não'}")

    pos_mase = {n: i for i, n in enumerate(ranking_mase)}
    pos_custo = {n: i for i, n in enumerate(ranking_custo)}

    fig, ax = plt.subplots(figsize=(8, 6.5))
    for n in ordem:
        ax.plot([0, 1], [pos_mase[n], pos_custo[n]], color=cores[n], linewidth=2, marker="o", markersize=9,
                 label=n, zorder=3)

    n_modelos = len(ordem)
    ax.set_xlim(-0.15, 1.15)
    ax.set_ylim(n_modelos - 0.5, -0.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Ranking por MASE\n(sazonal)", "Ranking por custo\ntotal"])
    ax.set_yticks(range(n_modelos))
    ax.set_yticklabels([f"{i+1}º" for i in range(n_modelos)])
    ax.set_ylabel("Posição no ranking (1º = melhor)")
    ax.grid(alpha=0.2, axis="y")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=4, fontsize=9)

    divergem = ranking_mase != ranking_custo
    ax.set_title(
        "SE/CO — Ranking por erro estatístico (MASE) vs. por custo de despacho (CMO)\n"
        + ("rankings DIVERGEM entre si — erro agregado não prevê custo de despacho"
           if divergem else "rankings coincidem")
    )
    _finalizar(fig, "resultado_6_erro_vs_custo.png")


def fig_calibracao(resultados: dict):
    modelos = ["SARIMA", "Prophet", "Chronos-2"]  # naive não tem quantis (previsão pontual sem incerteza)
    cores = {"SARIMA": COR_SARIMA, "Prophet": COR_PROPHET, "Chronos-2": COR_CHRONOS}

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([70, 100], [70, 100], color="#999999", linewidth=1, linestyle=":", label="Calibração perfeita", zorder=1)

    for nome in modelos:
        r = resultados[nome]
        nominais, empiricas = [80], [r["cobertura_80"] * 100]
        if r["cobertura_90"] is not None:
            nominais.append(90)
            empiricas.append(r["cobertura_90"] * 100)
        ax.plot(nominais, empiricas, color=cores[nome], linewidth=2, marker="o", markersize=10,
                 label=nome, zorder=3)
        for x, y in zip(nominais, empiricas):
            ax.annotate(f"{y:.1f}%", (x, y), textcoords="offset points", xytext=(6, 4), fontsize=8, color=cores[nome])

    ax.set_xlim(70, 100)
    ax.set_ylim(min(50, ax.get_ylim()[0]), 100)
    ax.set_xlabel("Cobertura nominal (%) — P10-P90 = 80%, P05-P95 = 90%")
    ax.set_ylabel("Cobertura empírica (%) — fração de horas com real dentro da banda")
    ax.set_title(f"SE/CO — Calibração dos intervalos de incerteza\nperíodo de avaliação {INICIO_AVALIACAO.date()}+")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.25)
    _finalizar(fig, "resultado_7_calibracao.png")


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    fig_heroi()
    fig_concentracao_custo()
    fig_efeito_temperatura()
    fig_quebras_estruturais()

    resultados = _coletar_resultados_4_modelos()
    fig_comparativo_4_modelos(resultados)
    fig_erro_vs_custo(resultados)
    fig_calibracao(resultados)


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
