"""Tarefa 3 da sanidade do SARIMA: testa se contexto maior (120d, 365d) melhora a
convergência do MLE sem custo proibitivo, contra o contexto atual (60d, commit
f87138a). Hipótese: a não-convergência vem do contexto curto (poucos ciclos para o
MLE fechar), não da natureza do método — mais dado ajuda a convergir sem mudar o
resultado assintotico (SARIMA satura).

NÃO roda o walk-forward completo com contexto maior — só uma amostra de origens,
comparando convergência, tempo e MASE nos mesmos pontos. Decisão de re-rodar o
walk-forward inteiro com contexto maior é do usuário, não deste script.
"""
import os

for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[var] = "1"

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_features import calcular_dst_ativo  # noqa: E402
from modelo_naive import CARGA_SE_PATH, INICIO_AVALIACAO, gerar_origens  # noqa: E402

ORDEM = (1, 1, 1)
ORDEM_SAZONAL = (1, 0, 1, 24)
CONTEXTOS_TESTADOS = {"60d": 1440, "120d": 2880, "365d": 8760}
N_AMOSTRAS = 20
SEED = 42


def ajustar(serie_alvo: pd.Series, origem: pd.Timestamp, contexto_horas: int) -> dict:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    idx_corte = serie_alvo.index.searchsorted(origem)
    historico = serie_alvo.iloc[:idx_corte]
    contexto = historico.iloc[-contexto_horas:]
    horas_alvo = pd.date_range(origem, periods=24, freq="h")
    y = contexto.to_numpy(dtype="float64")

    exog_hist = calcular_dst_ativo(pd.Series(contexto.index)).astype(float).to_numpy().reshape(-1, 1)
    exog_fut = calcular_dst_ativo(pd.Series(horas_alvo)).astype(float).to_numpy().reshape(-1, 1)

    t0 = time.time()
    modelo = SARIMAX(y, exog=exog_hist, order=ORDEM, seasonal_order=ORDEM_SAZONAL,
                      enforce_stationarity=False, enforce_invertibility=False)
    resultado = modelo.fit(disp=False)
    tempo = time.time() - t0
    prev = resultado.get_forecast(steps=24, exog=exog_fut)
    media = np.asarray(prev.predicted_mean)

    real = df_real.reindex(horas_alvo).to_numpy()
    erro_abs = np.abs(media - real)
    mae_local = float(np.nanmean(erro_abs))

    return {
        "convergiu": bool(resultado.mle_retvals.get("converged", False)),
        "tempo_s": tempo,
        "mae_local": mae_local,
        "n_contexto_real": len(contexto),
    }


def main():
    global df_real
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    origens = gerar_origens(df, INICIO_AVALIACAO)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()
    df_real = serie_alvo

    rng = np.random.default_rng(SEED)
    origens_amostra = [pd.Timestamp(o) for o in rng.choice(origens, size=N_AMOSTRAS, replace=False)]
    print(f"Testando {N_AMOSTRAS} origens amostradas (seed={SEED}) em contextos {list(CONTEXTOS_TESTADOS.keys())}")
    print(f"Ordem: SARIMA{ORDEM}x{ORDEM_SAZONAL}+dst (mesma do walk-forward de 60d)\n")

    resultados = {nome: [] for nome in CONTEXTOS_TESTADOS}

    for nome_ctx, horas_ctx in CONTEXTOS_TESTADOS.items():
        print(f"--- contexto {nome_ctx} ({horas_ctx}h) ---")
        for origem in origens_amostra:
            r = ajustar(serie_alvo, origem, horas_ctx)
            resultados[nome_ctx].append(r)
            print(f"  {origem.date()}: convergiu={r['convergiu']} tempo={r['tempo_s']:.2f}s "
                  f"mae_local={r['mae_local']:.2f} n_contexto={r['n_contexto_real']}")
        tempos = [r["tempo_s"] for r in resultados[nome_ctx]]
        n_conv = sum(r["convergiu"] for r in resultados[nome_ctx])
        maes = [r["mae_local"] for r in resultados[nome_ctx]]
        print(f"  RESUMO {nome_ctx}: convergência={n_conv}/{N_AMOSTRAS} ({n_conv/N_AMOSTRAS*100:.1f}%), "
              f"tempo médio={np.mean(tempos):.2f}s, tempo total amostra={sum(tempos):.1f}s, "
              f"MAE médio local={np.mean(maes):.2f}")
        print(f"  Extrapolação p/ 927 origens: {np.mean(tempos)*927/60:.1f} min\n")

    print("\n=== COMPARAÇÃO ENTRE CONTEXTOS (mesmas 20 origens) ===")
    for nome_ctx in CONTEXTOS_TESTADOS:
        tempos = [r["tempo_s"] for r in resultados[nome_ctx]]
        n_conv = sum(r["convergiu"] for r in resultados[nome_ctx])
        maes = [r["mae_local"] for r in resultados[nome_ctx]]
        print(f"{nome_ctx}: convergência={n_conv}/{N_AMOSTRAS}, tempo médio/origem={np.mean(tempos):.2f}s, "
              f"MAE médio={np.mean(maes):.2f}, extrapolação 927 origens={np.mean(tempos)*927/60:.1f} min")

    print("\nDecisão de re-rodar o walk-forward completo com contexto maior é do usuário — "
          "este script só reporta, não decide.")


if __name__ == "__main__":
    main()
