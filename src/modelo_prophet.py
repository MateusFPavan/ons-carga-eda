"""Prophet — baseline clássico, grupo de controle da extensão (1) do escopo (ver
reports/ESCOPO.md seções 9, 11, 12, 13). Ao contrário do SARIMA (satura, contexto
curto), o Prophet USA histórico longo para estimar tendência e sazonalidade anual
— por isso o contexto aqui é de 2 anos, uma decisão de método, não de orçamento.

Sazonalidades: diária, semanal, anual (Fourier padrão do Prophet). Feriados: usa a
feature `is_feriado` já existente (calcular_is_feriado, mesma função de
gerar_features.py) como regressor extra, em vez do `add_country_holidays` nativo do
Prophet — para manter uma única definição de feriado no projeto inteiro (a mesma
biblioteca `holidays`, a mesma chamada), não duas fontes divergentes. dst_ativo
também entra como regressor extra — mesma decisão do SARIMA.

Temperatura NÃO é passada (camada secundária, fora do modelo principal — FACTS.md
seção H).

Intervalos 80% e 90% vêm de UM único fit via `predictive_samples()` (1000
trajetórias simuladas), não de dois fits com `interval_width` diferente — evita
dobrar o custo computacional só para ter dois níveis de cobertura.

Reusa gerar_origens, rodar_walkforward, avaliar_modelo, testar_vazamento,
calcular_mae_insample_naive1/sazonal, checar_cobertura_cmo, carregar_cmo_horario_se,
calcular_custo de src/modelo_naive.py — não reimplementa nada disso.

NOTA SOBRE O TESTE DE VAZAMENTO (commit f87138a vs. sanidade seguinte): a primeira
rodada completa reportou 720/720 "divergências" no teste de vazamento. PROVADO (não
suposto) em src/verificar_determinismo_prophet.py que a causa é não-determinismo
numérico do otimizador Stan/L-BFGS do Prophet (threading de BLAS/OpenMP e ausência
de seed fixa) — com STAN_NUM_THREADS/OMP_NUM_THREADS/MKL_NUM_THREADS/
OPENBLAS_NUM_THREADS/NUMEXPR_NUM_THREADS/VECLIB_MAXIMUM_THREADS=1 e seed fixa
passada a `Prophet.fit(..., seed=...)`, as mesmas 30 origens amostradas bateram
bit a bit (0/720 divergências) — NÃO é vazamento de dado do dia D. Este script não
fixa essas variáveis (o walk-forward completo já rodou e os números da tabela
comparativa são válidos); qualquer nova rodada completa de Prophet deveria fixá-las
para manter o teste de vazamento confiável.
"""
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_features import calcular_dst_ativo, calcular_is_feriado  # noqa: E402
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, INICIO_AVALIACAO, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO,
    SanityCheckError, avaliar_modelo, calcular_custo, calcular_mae_insample_naive1,
    calcular_mae_insample_naive_sazonal, carregar_cmo_horario_se, checar_cobertura_cmo,
    gerar_origens, rodar_walkforward, testar_vazamento, verificar_grade_regular,
)

CONTEXTO_H = 17520  # 2 anos — decisão de método (tendência/sazonalidade anual)


def previsor_prophet(contexto_horas: int, cache: dict):
    from prophet import Prophet

    def prever(historico: pd.Series, origem: pd.Timestamp) -> pd.Series:
        contexto = historico.iloc[-contexto_horas:]
        horas_alvo = pd.date_range(origem, periods=24, freq="h")

        train = pd.DataFrame({"ds": contexto.index, "y": contexto.values})
        train["dst_ativo"] = calcular_dst_ativo(train["ds"]).astype(float).values
        train["is_feriado"] = calcular_is_feriado(train["ds"]).astype(float).values

        m = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=True)
        m.add_regressor("dst_ativo")
        m.add_regressor("is_feriado")
        m.fit(train)

        futuro = pd.DataFrame({"ds": horas_alvo})
        futuro["dst_ativo"] = calcular_dst_ativo(futuro["ds"]).astype(float).values
        futuro["is_feriado"] = calcular_is_feriado(futuro["ds"]).astype(float).values

        amostras = m.predictive_samples(futuro)["yhat"]  # (24, 1000)
        p05, p10, mediana, p90, p95 = np.percentile(amostras, [5, 10, 50, 90, 95], axis=1)
        cache[origem] = {"p05": p05, "p10": p10, "p90": p90, "p95": p95}
        return pd.Series(mediana, index=horas_alvo)
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
          f"Prophet, contexto={CONTEXTO_H}h ({CONTEXTO_H//8760} anos), regressores=dst_ativo+is_feriado")

    mae1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)

    cobertura_cmo = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"]) if cobertura_cmo["completo"] else None

    cache = {}
    previsor = previsor_prophet(CONTEXTO_H, cache)

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
    teste = testar_vazamento(serie_alvo, previsto, previsor, "Prophet", N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
    if teste["divergencias"]:
        print(f"{len(teste['divergencias'])} DIVERGÊNCIA(S):", file=sys.stderr)
        for d_ in teste["divergencias"][:10]:
            print(f"  - {d_}", file=sys.stderr)
        raise SanityCheckError("Teste de vazamento falhou para Prophet.")
    print(f"OK — {teste['n_comparacoes']} comparações, 0 divergências.")

    print("\n=== RESUMO_PROPHET_JSON ===")
    import json
    print(json.dumps({
        "modelo": "Prophet(d+w+y,dst,feriado)", "contexto_h": CONTEXTO_H,
        "mape": resultado["mape"], "rmse": resultado["rmse"],
        "mase_naive1": resultado["mase_naive1"], "mase_sazonal": resultado["mase_sazonal"],
        "custo_total": custo["custo_total"] if custo else None,
        "cobertura_80": cobertura_80, "cobertura_90": cobertura_90,
        "tempo_s": tempo_execucao,
    }))


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
