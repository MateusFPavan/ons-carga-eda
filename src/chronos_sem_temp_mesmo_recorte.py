"""Recomputa Chronos-2 120M @2048h SEM temperatura, mas restrito ao MESMO recorte
(2024-01-20+) do run com temperatura (data/processed/chronos_temp_previsoes.parquet),
para a comparação com/sem ser justa (mesmo período, não 2024-01-01+ vs. 2024-01-20+).
Reusa a mesma config vencedora do commit 59b8dc4, só muda a origem inicial.
"""
import os
for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[var] = "1"

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO, avaliar_modelo,
    calcular_custo, calcular_mae_insample_naive1, calcular_mae_insample_naive_sazonal,
    carregar_cmo_horario_se, checar_cobertura_cmo, gerar_origens, rodar_walkforward,
    testar_vazamento, verificar_grade_regular,
)
from modelo_chronos2 import previsor_chronos2  # noqa: E402

INICIO_TEMP = pd.Timestamp("2024-01-20")
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def main():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_TEMP)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()
    print(f"Período: {INICIO_TEMP.date()} a {fim_serie.date()} — {len(origens)} origens (mesmo recorte do run com temperatura)")

    mae1, _ = calcular_mae_insample_naive1(df, INICIO_TEMP)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_TEMP, 168)
    cobertura_cmo = checar_cobertura_cmo(INICIO_TEMP.year, fim_serie.year)
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"]) if cobertura_cmo["completo"] else None

    from chronos import BaseChronosPipeline
    pipeline = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
    cache = {}
    previsor = previsor_chronos2(pipeline, 2048, cache)

    t0 = time.time()
    previsto = rodar_walkforward(serie_alvo, origens, previsor)
    print(f"walk-forward: {time.time()-t0:.1f}s")

    resultado = avaliar_modelo(df, previsto, mae1, mae_saz)
    custo = calcular_custo(resultado["avaliacao"], cmo_horario) if cmo_horario is not None else None
    print(f"MAPE={resultado['mape']:.4f}% RMSE={resultado['rmse']:.2f} "
          f"MASE(1passo)={resultado['mase_naive1']:.4f} MASE(sazonal)={resultado['mase_sazonal']:.4f}")
    print(f"Custo total: R$ {custo['custo_total']:,.2f}" if custo else "Custo: N/D")

    teste = testar_vazamento(serie_alvo, previsto, previsor, "Chronos_sem_temp_mesmo_recorte", N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
    print(f"Vazamento: {teste['n_comparacoes']} comparações, {len(teste['divergencias'])} divergências")

    resultado["avaliacao"].to_parquet(PROCESSED_DIR / "chronos_sem_temp_mesmo_recorte.parquet", index=False)
    print(f"Salvo em {PROCESSED_DIR / 'chronos_sem_temp_mesmo_recorte.parquet'}")


if __name__ == "__main__":
    main()
