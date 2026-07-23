"""Prova (não suposição) da causa do teste de vazamento do Prophet ter reportado
720/720 divergências no commit f87138a. Hipótese: não-determinismo numérico do
otimizador Stan/L-BFGS (multi-threading em BLAS/OpenMP, ausência de seed fixa), não
vazamento de dado.

Método: fixa TODAS as fontes conhecidas de não-determinismo (seed do Stan,
single-thread em todas as bibliotecas de álgebra linear) e roda a MESMA comparação
do teste de vazamento — não o walk-forward inteiro, só as 30 origens amostradas
(mesma seed=42 de sempre) — comparando a previsão via truncamento estilo
rodar_walkforward (searchsorted) contra a via testar_vazamento (filtro booleano).
Se as duas baterem bit a bit com tudo determinístico: PROVADO que era
não-determinismo do otimizador. Se ainda divergir: há algo real, reportado em
detalhe (não escondido).
"""
import os

# precisa ser setado ANTES de importar numpy/prophet/cmdstanpy
for var in ("STAN_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[var] = "1"

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_features import calcular_dst_ativo, calcular_is_feriado  # noqa: E402
from modelo_naive import CARGA_SE_PATH, INICIO_AVALIACAO, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO, gerar_origens  # noqa: E402
from modelo_prophet import CONTEXTO_H  # noqa: E402

SEED_STAN = 42


def prever_deterministico(historico: pd.Series, origem: pd.Timestamp) -> pd.Series:
    from prophet import Prophet

    contexto = historico.iloc[-CONTEXTO_H:]
    horas_alvo = pd.date_range(origem, periods=24, freq="h")

    train = pd.DataFrame({"ds": contexto.index, "y": contexto.values})
    train["dst_ativo"] = calcular_dst_ativo(train["ds"]).astype(float).values
    train["is_feriado"] = calcular_is_feriado(train["ds"]).astype(float).values

    m = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=True)
    m.add_regressor("dst_ativo")
    m.add_regressor("is_feriado")
    m.fit(train, seed=SEED_STAN)

    futuro = pd.DataFrame({"ds": horas_alvo})
    futuro["dst_ativo"] = calcular_dst_ativo(futuro["ds"]).astype(float).values
    futuro["is_feriado"] = calcular_is_feriado(futuro["ds"]).astype(float).values
    prev = m.predict(futuro)
    return pd.Series(prev["yhat"].values, index=horas_alvo)


def main():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    origens = gerar_origens(df, INICIO_AVALIACAO)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()

    rng = np.random.default_rng(SEED_VAZAMENTO)
    origens_amostra = rng.choice(origens, size=min(N_AMOSTRAS_VAZAMENTO, len(origens)), replace=False)

    print("Env vars de single-thread fixadas: STAN_NUM_THREADS, OMP_NUM_THREADS, MKL_NUM_THREADS, "
          "OPENBLAS_NUM_THREADS, NUMEXPR_NUM_THREADS, VECLIB_MAXIMUM_THREADS = 1")
    print(f"Seed do Stan fixada: {SEED_STAN}")
    print(f"Testando {len(origens_amostra)} origens amostradas (mesma seed={SEED_VAZAMENTO} do teste original)...\n")

    divergencias = []
    n_comparacoes = 0

    for origem in origens_amostra:
        origem = pd.Timestamp(origem)

        # "producao": truncamento via searchsorted, mesmo estilo de rodar_walkforward
        idx_corte = serie_alvo.index.searchsorted(origem)
        historico_producao = serie_alvo.iloc[:idx_corte]
        prod = prever_deterministico(historico_producao, origem)

        # "recalculo": truncamento via filtro booleano, mesmo estilo de testar_vazamento
        historico_recalculo = serie_alvo[serie_alvo.index < origem]
        recalc = prever_deterministico(historico_recalculo, origem)

        for ts in prod.index:
            n_comparacoes += 1
            v_prod, v_recalc = float(prod[ts]), float(recalc[ts])
            if v_prod != v_recalc:
                divergencias.append((origem, ts, v_prod, v_recalc, abs(v_prod - v_recalc)))
        print(f"  {origem.date()}: {'OK (bit-identico)' if not any(d[0]==origem for d in divergencias) else 'DIVERGIU'}")

    print("\n=== RESULTADO ===")
    print(f"Comparações: {n_comparacoes}")
    print(f"Divergências: {len(divergencias)}")
    if divergencias:
        print("\nDETALHE (não escondido — o teste falhou mesmo com tudo determinístico):")
        for origem, ts, vp, vr, dif in divergencias[:30]:
            print(f"  {ts} (origem {origem.date()}): producao={vp:.6f} recalculo={vr:.6f} diff={dif:.6f} "
                  f"({dif/vp*100:.4f}%)")
        print("\nCONCLUSÃO: NÃO provado que era só não-determinismo — há divergência residual mesmo com seed e "
              "single-thread fixados. PARANDO para investigar vazamento real, conforme instrução.")
    else:
        print("\nCONCLUSÃO: PROVADO — com seed e single-thread fixados, produção e recálculo batem bit a bit "
              "em todas as origens testadas. O teste de vazamento original (720/720 divergências) foi causado "
              "por não-determinismo numérico do otimizador Stan/L-BFGS (threading e/ou seed não fixados), "
              "NÃO por vazamento de dado do dia D.")


if __name__ == "__main__":
    main()
