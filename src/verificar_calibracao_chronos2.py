"""Duas checagens de sanidade sobre o resultado do Chronos-2 (commit 59b8dc4), antes
de construir em cima dele — não é modelo novo, não é métrica nova:

1. Nível nominal do intervalo de calibração usado (P10-P90 = 80%, não 90%) e
   cobertura empírica contra o nominal CORRETO, mais um segundo intervalo (P5-P95 =
   90% nominal) para comparar com Simeone (2026), que usou 90% nominal.
2. O que a documentação oficial do Chronos-2 diz sobre o corpus de pré-treino
   (risco de contaminação) — ver relatório separado no stdout desta rodada.

Não salva as previsões originais do commit 59b8dc4 em disco, então recalcula só a
ÚNICA combinação necessária (chronos2_120M @ 2048h, a config vencedora) — não a
varredura de 10 combinações inteira. Reusa rodar_walkforward, avaliar_modelo e
testar_vazamento de src/modelo_naive.py sem alteração.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, INICIO_AVALIACAO, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO,
    SanityCheckError, avaliar_modelo, calcular_mae_insample_naive1,
    calcular_mae_insample_naive_sazonal, gerar_origens, rodar_walkforward,
    testar_vazamento, verificar_grade_regular,
)

CHECKPOINT = "amazon/chronos-2"
CONTEXTO_H = 2048
QUANTIS = [0.05, 0.1, 0.5, 0.9, 0.95]

# valores originais do commit 59b8dc4 (chronos2_120M @ 2048h), só para o print de
# comparação abaixo — não usados em nenhum cálculo
MAPE_ORIGINAL = 1.8235
MASE_SAZONAL_ORIGINAL = 0.4363


def previsor_chronos2_calibracao(pipeline, contexto_horas: int, cache: dict):
    def prever(historico: pd.Series, origem: pd.Timestamp) -> pd.Series:
        contexto = historico.iloc[-contexto_horas:].to_numpy(dtype="float32")
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        quantis, _ = pipeline.predict_quantiles(
            inputs=[{"target": contexto}], prediction_length=24, quantile_levels=QUANTIS,
        )
        arr = np.asarray(quantis[0][0])  # (24, 5): p5, p10, mediana, p90, p95
        cache[origem] = {"p5": arr[:, 0], "p10": arr[:, 1], "mediana": arr[:, 2], "p90": arr[:, 3], "p95": arr[:, 4]}
        return pd.Series(arr[:, 2], index=horas_alvo)
    return prever


def main():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    origens = gerar_origens(df, INICIO_AVALIACAO)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()

    mae_naive1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_naive_sazonal, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)

    print(f"Recalculando chronos2_120M @ {CONTEXTO_H}h com quantis {QUANTIS} "
          f"({len(origens)} origens)...")
    from chronos import BaseChronosPipeline
    pipeline = BaseChronosPipeline.from_pretrained(CHECKPOINT, device_map="cpu")

    cache = {}
    previsor = previsor_chronos2_calibracao(pipeline, CONTEXTO_H, cache)
    previsto = rodar_walkforward(serie_alvo, origens, previsor)
    resultado = avaliar_modelo(df, previsto, mae_naive1, mae_naive_sazonal)

    print(f"\nRecalculo: MAPE={resultado['mape']:.4f}% MASE(sazonal)={resultado['mase_sazonal']:.4f}")
    print(f"Original (commit 59b8dc4): MAPE={MAPE_ORIGINAL:.4f}% MASE(sazonal)={MASE_SAZONAL_ORIGINAL:.4f}")
    print(f"Batem (mesmo modelo/contexto/dado, esperado bit-idêntico ou muito próximo): "
          f"{'sim' if abs(resultado['mape'] - MAPE_ORIGINAL) < 0.01 else 'NÃO — investigar'}")

    print(f"\nTestando vazamento: {N_AMOSTRAS_VAZAMENTO} origens aleatórias (seed={SEED_VAZAMENTO})...")
    teste = testar_vazamento(serie_alvo, previsto, previsor, "chronos2_120M@2048h_calibracao",
                              N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
    if teste["divergencias"]:
        print(f"{len(teste['divergencias'])} DIVERGÊNCIA(S):", file=sys.stderr)
        for d in teste["divergencias"][:10]:
            print(f"  - {d}", file=sys.stderr)
        raise SanityCheckError("Teste de vazamento falhou no recálculo de calibração.")
    print(f"OK — {teste['n_comparacoes']} comparações, 0 divergências.")

    # --- montar dataframe de calibração e calcular as duas coberturas
    linhas = []
    for origem, d in cache.items():
        horas = pd.date_range(origem, periods=24, freq="h")
        for i, h in enumerate(horas):
            linhas.append({"din_instante": h, "p5": d["p5"][i], "p10": d["p10"][i], "p90": d["p90"][i], "p95": d["p95"][i]})
    calib = pd.DataFrame(linhas)

    incluida = resultado["avaliacao"][resultado["avaliacao"]["motivo_exclusao"] == "incluida"].copy()
    m = incluida.merge(calib, on="din_instante", how="left", validate="one_to_one")

    cobertura_80 = float(((m["real"] >= m["p10"]) & (m["real"] <= m["p90"])).mean())
    cobertura_90 = float(((m["real"] >= m["p5"]) & (m["real"] <= m["p95"])).mean())
    n_avaliado = len(m)

    print("\n=== TAREFA 1: nível nominal e cobertura ===")
    print(f"Intervalo [P10, P90]: nível nominal = 0,90 - 0,10 = 0,80 (80%), NÃO 90%.")
    print(f"  Cobertura empírica: {cobertura_80*100:.2f}% (n={n_avaliado}) vs. nominal 80% "
          f"-> diferença = {cobertura_80*100 - 80:+.2f}pp")
    print(f"Intervalo [P5, P95]: nível nominal = 0,95 - 0,05 = 0,90 (90%) — comparável a Simeone.")
    print(f"  Cobertura empírica: {cobertura_90*100:.2f}% (n={n_avaliado}) vs. nominal 90% "
          f"-> diferença = {cobertura_90*100 - 90:+.2f}pp")

    print("\nConclusão factual:")
    print(f"  A 80% nominal: cobertura empírica {cobertura_80*100:.2f}% — "
          f"{'próxima do nominal (bem calibrado)' if abs(cobertura_80*100-80) <= 3 else ('subcoberto/superconfiante' if cobertura_80*100 < 80 else 'sobrecoberto/subconfiante')}.")
    print(f"  A 90% nominal: cobertura empírica {cobertura_90*100:.2f}% — "
          f"{'próxima do nominal (bem calibrado)' if abs(cobertura_90*100-90) <= 3 else ('subcoberto/superconfiante' if cobertura_90*100 < 90 else 'sobrecoberto/subconfiante')}.")
    print(f"  Simeone (2026): ~95% empírico a 90% nominal (+5pp, levemente conservador/subconfiante).")
    print(f"  Aqui (SE/CO): {cobertura_90*100:.2f}% empírico a 90% nominal "
          f"({cobertura_90*100-90:+.2f}pp).")


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
