"""SARIMA — baseline clássico, grupo de controle da extensão (1) do escopo (ver
reports/ESCOPO.md seções 9, 11, 12, 13). Papel no projeto: SARIMA estima poucos
coeficientes da estrutura de autocorrelação recente e SATURA depois de alguns
ciclos sazonais — mais dado não o melhora, só custa CPU. Por isso o contexto
(60 dias) é uma decisão de método, não de orçamento: ~8,5 ciclos semanais bastam
para os coeficientes sazonais assentarem. Isto contrasta com o Chronos-2 (contexto
longo ajuda) e o Prophet (usa histórico longo para tendência/sazonalidade anual).

Ordem escolhida com evidência, não reflexo — ver ADF/KPSS rodados nesta sondagem
(4 janelas representativas de 60 dias, espalhadas por 2023-2026): ao nível bruto,
ADF sempre rejeita raiz unitária (p≈0) mas KPSS rejeita estacionariedade em 3 de 4
janelas (p=0,01) — conflito clássico ADF-estacionário/KPSS-não-estacionário. Após
1 diferença regular (d=1), ADF e KPSS concordam em estacionariedade nas 4 janelas.
Diferenciação sazonal adicional (D=1) não muda essa conclusão nem foi necessária
além de d=1. Decisão: d=1, D=0 — sazonalidade diária capturada pelos termos AR/MA
sazonais em s=24, não por diferenciação sazonal. Ordem final: (1,1,1)(1,0,1,24) —
razoável, não vem de busca em grade (SARIMA é baseline, não otimizado
exaustivamente, por restrição explícita da tarefa).

dst_ativo entra como exógena (SARIMAX) — testado e barato o suficiente (+33% no
tempo de fit numa amostra) para incluir.

Reusa gerar_origens, rodar_walkforward, avaliar_modelo, testar_vazamento,
calcular_mae_insample_naive1/sazonal, checar_cobertura_cmo, carregar_cmo_horario_se,
calcular_custo de src/modelo_naive.py — não reimplementa nada disso. dst_ativo vem
de src/gerar_features.py (calcular_dst_ativo), mesma função usada em toda a parte.

Salva previsões + flag de convergência do MLE por origem em
data/processed/sarima_previsoes_60d.parquet — para nunca mais precisar re-rodar
(~82min) só para diagnosticar convergência (commit f87138a não salvou nada).
Single-thread forçado (BLAS/OpenMP) para o teste de vazamento ser confiável desde
já — mesma precaução do Prophet (src/verificar_determinismo_prophet.py), mesmo
sem evidência de que SARIMA precise (já passou 0/720 sem isso antes).
"""
import os

for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[var] = "1"

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUT_PATH = PROCESSED_DIR / "sarima_previsoes_60d.parquet"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_features import calcular_dst_ativo  # noqa: E402
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, INICIO_AVALIACAO, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO,
    SanityCheckError, avaliar_modelo, calcular_custo, calcular_mae_insample_naive1,
    calcular_mae_insample_naive_sazonal, carregar_cmo_horario_se, checar_cobertura_cmo,
    gerar_origens, rodar_walkforward, testar_vazamento, verificar_grade_regular,
)

CONTEXTO_H = 1440  # 60 dias — decisão de método (SARIMA satura), não de orçamento
ORDEM = (1, 1, 1)
ORDEM_SAZONAL = (1, 0, 1, 24)
USAR_EXOGENA_DST = True


def previsor_sarima(ordem, ordem_sazonal, contexto_horas: int, usar_exog: bool, cache: dict):
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    def prever(historico: pd.Series, origem: pd.Timestamp) -> pd.Series:
        contexto = historico.iloc[-contexto_horas:]
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        y = contexto.to_numpy(dtype="float64")

        exog_hist = exog_fut = None
        if usar_exog:
            exog_hist = calcular_dst_ativo(pd.Series(contexto.index)).astype(float).to_numpy().reshape(-1, 1)
            exog_fut = calcular_dst_ativo(pd.Series(horas_alvo)).astype(float).to_numpy().reshape(-1, 1)

        modelo = SARIMAX(y, exog=exog_hist, order=ordem, seasonal_order=ordem_sazonal,
                          enforce_stationarity=False, enforce_invertibility=False)
        resultado = modelo.fit(disp=False)
        prev = resultado.get_forecast(steps=24, exog=exog_fut)
        media = np.asarray(prev.predicted_mean)
        ic80 = np.asarray(prev.conf_int(alpha=0.20))  # 80% nominal
        ic90 = np.asarray(prev.conf_int(alpha=0.10))  # 90% nominal

        convergiu = bool(resultado.mle_retvals.get("converged", False))
        cache[origem] = {
            "p10": ic80[:, 0], "p90": ic80[:, 1], "p05": ic90[:, 0], "p95": ic90[:, 1],
            "convergiu": convergiu,
        }
        return pd.Series(media, index=horas_alvo)
    return prever


def main():
    if not CARGA_SE_PATH.exists():
        raise SanityCheckError(f"Arquivo ausente: {CARGA_SE_PATH}")

    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_AVALIACAO)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()
    print(f"Período: {INICIO_AVALIACAO.date()} a {fim_serie.date()} — {len(origens)} origens. "
          f"SARIMA{ORDEM}x{ORDEM_SAZONAL}, contexto={CONTEXTO_H}h, exog_dst={USAR_EXOGENA_DST}")

    mae1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)

    cobertura_cmo = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"]) if cobertura_cmo["completo"] else None

    cache = {}
    previsor = previsor_sarima(ORDEM, ORDEM_SAZONAL, CONTEXTO_H, USAR_EXOGENA_DST, cache)

    t0 = time.time()
    previsto = rodar_walkforward(serie_alvo, origens, previsor)
    tempo_execucao = time.time() - t0
    print(f"walk-forward: {len(origens)} origens em {tempo_execucao:.1f}s ({tempo_execucao/60:.1f} min, "
          f"{tempo_execucao/len(origens)*1000:.1f}ms/origem)")

    resultado = avaliar_modelo(df, previsto, mae1, mae_saz)

    linhas = []
    for origem, d in cache.items():
        horas = pd.date_range(origem, periods=24, freq="h")
        for i, h in enumerate(horas):
            linhas.append({"din_instante": h, "p05": d["p05"][i], "p10": d["p10"][i], "p90": d["p90"][i], "p95": d["p95"][i]})
    calib = pd.DataFrame(linhas)
    incluida = resultado["avaliacao"][resultado["avaliacao"]["motivo_exclusao"] == "incluida"].copy()
    m = incluida.merge(calib, on="din_instante", how="left", validate="one_to_one")
    cobertura_80 = float(((m["real"] >= m["p10"]) & (m["real"] <= m["p90"])).mean())
    cobertura_90 = float(((m["real"] >= m["p05"]) & (m["real"] <= m["p95"])).mean())

    custo = calcular_custo(resultado["avaliacao"], cmo_horario) if cmo_horario is not None else None

    print(f"\nMAPE={resultado['mape']:.4f}% RMSE={resultado['rmse']:.2f} "
          f"MASE(1passo)={resultado['mase_naive1']:.4f} MASE(sazonal)={resultado['mase_sazonal']:.4f}")
    print(f"Cobertura 80%: {cobertura_80*100:.2f}% | Cobertura 90%: {cobertura_90*100:.2f}%")
    print(f"Custo total: R$ {custo['custo_total']:,.2f}" if custo else "Custo: N/D (CMO incompleto)")

    print(f"\nTestando vazamento: {N_AMOSTRAS_VAZAMENTO} origens aleatórias (seed={SEED_VAZAMENTO})...")
    teste = testar_vazamento(serie_alvo, previsto, previsor, "SARIMA", N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
    if teste["divergencias"]:
        print(f"{len(teste['divergencias'])} DIVERGÊNCIA(S):", file=sys.stderr)
        for d_ in teste["divergencias"][:10]:
            print(f"  - {d_}", file=sys.stderr)
        raise SanityCheckError("Teste de vazamento falhou para SARIMA.")
    print(f"OK — {teste['n_comparacoes']} comparações, 0 divergências.")

    # --- diagnóstico de convergência (Tarefa 2)
    conv_df = pd.DataFrame([{"origem": o, "convergiu": d["convergiu"]} for o, d in cache.items()])
    n_total_origens = len(conv_df)
    n_nao_convergiu = int((~conv_df["convergiu"]).sum())
    pct_nao_convergiu = n_nao_convergiu / n_total_origens * 100
    print(f"\n=== CONVERGÊNCIA DO MLE ===")
    print(f"Origens que NÃO convergiram: {n_nao_convergiu}/{n_total_origens} ({pct_nao_convergiu:.2f}%)")

    avaliacao = resultado["avaliacao"].copy()
    avaliacao["origem"] = avaliacao["din_instante"].dt.normalize()
    mapa_conv = dict(zip(conv_df["origem"], conv_df["convergiu"]))
    avaliacao["convergiu"] = avaliacao["origem"].map(mapa_conv)

    def metricas_subconjunto(sub: pd.DataFrame) -> dict:
        mape_ = float((sub["erro"].abs() / sub["real"].abs()).mean() * 100)
        rmse_ = float(np.sqrt((sub["erro"] ** 2).mean()))
        mae_ = float(sub["erro"].abs().mean())
        return {"n": len(sub), "mape": mape_, "rmse": rmse_, "mae": mae_,
                "mase_naive1": mae_ / mae1, "mase_sazonal": mae_ / mae_saz}

    incl_todas = avaliacao[avaliacao["motivo_exclusao"] == "incluida"]
    incl_convergentes = incl_todas[incl_todas["convergiu"] == True]  # noqa: E712
    met_a = metricas_subconjunto(incl_todas)
    met_b = metricas_subconjunto(incl_convergentes)

    avaliacao_b = avaliacao.copy()
    avaliacao_b.loc[avaliacao_b["convergiu"] != True, "motivo_exclusao"] = "nao_convergiu"  # noqa: E712
    custo_b = calcular_custo(avaliacao_b, cmo_horario) if cmo_horario is not None else None

    print(f"\n(a) TODAS as {n_total_origens} origens: n_horas={met_a['n']} MAPE={met_a['mape']:.4f}% "
          f"RMSE={met_a['rmse']:.2f} MASE(sazonal)={met_a['mase_sazonal']:.4f} "
          f"custo=R$ {custo['custo_total']:,.2f}" if custo else "")
    print(f"(b) SÓ CONVERGENTES ({n_total_origens - n_nao_convergiu} origens): n_horas={met_b['n']} "
          f"MAPE={met_b['mape']:.4f}% RMSE={met_b['rmse']:.2f} MASE(sazonal)={met_b['mase_sazonal']:.4f} "
          f"custo=R$ {custo_b['custo_total']:,.2f}" if custo_b else "")

    if n_nao_convergiu:
        nao_conv = conv_df[~conv_df["convergiu"]]
        por_mes = nao_conv["origem"].dt.to_period("M").value_counts().sort_index()
        print("\nDistribuição mensal das não-convergências:")
        print(por_mes.to_string())

    # --- salvar previsões + flags em disco (nunca mais precisar re-rodar só p/ diagnosticar)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    saida = avaliacao[["din_instante", "origem", "previsto", "real", "motivo_exclusao", "convergiu"]].merge(
        calib, on="din_instante", how="left"
    )
    saida.to_parquet(OUT_PATH, index=False)
    print(f"\nPrevisões + flags de convergência + intervalos salvos em: {OUT_PATH}")

    print("\n=== RESUMO_SARIMA_JSON ===")
    print(json.dumps({
        "modelo": "SARIMA(1,1,1)(1,0,1,24)+dst", "contexto_h": CONTEXTO_H,
        "mape": resultado["mape"], "rmse": resultado["rmse"],
        "mase_naive1": resultado["mase_naive1"], "mase_sazonal": resultado["mase_sazonal"],
        "custo_total": custo["custo_total"] if custo else None,
        "cobertura_80": cobertura_80, "cobertura_90": cobertura_90,
        "tempo_s": tempo_execucao,
        "n_nao_convergiu": n_nao_convergiu, "pct_nao_convergiu": pct_nao_convergiu,
        "metricas_todas": met_a, "metricas_convergentes": met_b,
        "custo_convergentes": custo_b["custo_total"] if custo_b else None,
    }))


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
