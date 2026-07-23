"""Tarefa B: extrai o número limpo do SARIMAX+temperatura das previsões JÁ salvas
(data/processed/sarimax_temp_previsoes.parquet) — não re-roda o walk-forward.
Filtra por convergência + plausibilidade, calcula métricas, compara com SARIMAX
sem temperatura no mesmo recorte (2024-01-20+).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, calcular_custo, calcular_mae_insample_naive1,
    calcular_mae_insample_naive_sazonal, carregar_cmo_horario_se, checar_cobertura_cmo,
)

INICIO_TEMP = pd.Timestamp("2024-01-20")
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def metricas(sub: pd.DataFrame, mae1: float, mae_saz: float, cmo_horario) -> dict:
    erro = sub["previsto"] - sub["real"]
    mape = float((erro.abs() / sub["real"].abs()).mean() * 100)
    rmse = float(np.sqrt((erro ** 2).mean()))
    mae = float(erro.abs().mean())
    resultado = {"n": len(sub), "mape": mape, "rmse": rmse, "mae": mae,
                 "mase_naive1": mae / mae1, "mase_sazonal": mae / mae_saz}
    if cmo_horario is not None:
        aval = sub[["din_instante", "previsto", "real"]].copy()
        aval["motivo_exclusao"] = "incluida"
        aval["erro"] = erro
        custo = calcular_custo(aval, cmo_horario)
        resultado["custo_total"] = custo["custo_total"]
        resultado["n_incluida_custo"] = custo["n_incluida_custo"]
    return resultado


def main():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    fim_serie = df["din_instante"].max()
    mae1, _ = calcular_mae_insample_naive1(df, INICIO_TEMP)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_TEMP, 168)
    cobertura_cmo = checar_cobertura_cmo(INICIO_TEMP.year, fim_serie.year)
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"]) if cobertura_cmo["completo"] else None

    sarimax = pd.read_parquet(PROCESSED_DIR / "sarimax_temp_previsoes.parquet")
    real = df.set_index("din_instante")["val_cargaenergiahomwmed"]
    sarimax["real"] = sarimax["din_instante"].map(real)

    max_historico = df["val_cargaenergiahomwmed"].max()
    limite_plausivel = 2 * max_historico

    conv_por_origem = sarimax.groupby("origem")["convergiu"].first()
    n_origens = len(conv_por_origem)
    n_convergiu = int(conv_por_origem.sum())
    print(f"Taxa de convergência SARIMAX+temp: {n_convergiu}/{n_origens} ({n_convergiu/n_origens*100:.2f}%)")
    print("Taxa de convergência SARIMAX sem temp (commit 0339234): 904/927 (97.52%)")
    print(f"Contraste: {97.52 - n_convergiu/n_origens*100:.2f}pp de queda na convergência ao adicionar 6 exógenas "
          f"(dst_ativo + 5 temperaturas)\n")

    d1 = sarimax[sarimax["convergiu"] == True].dropna(subset=["real", "previsto"])  # noqa: E712
    d2 = d1[(d1["previsto"] >= 0) & (d1["previsto"] <= limite_plausivel)]
    print(f"Após filtro convergiu=True: {len(d1)} horas ({d1['origem'].nunique()} origens)")
    print(f"Após filtro de plausibilidade adicional [0, {limite_plausivel:.0f}]: {len(d2)} horas "
          f"({d2['origem'].nunique()} origens) — {len(d1)-len(d2)} descartadas por implausibilidade "
          f"apesar de convergiu=True")

    m = metricas(d2, mae1, mae_saz, cmo_horario)
    print("\n=== SARIMAX+temp LIMPO (só convergentes + plausíveis) ===")
    print(f"n={m['n']} horas | MAPE={m['mape']:.4f}% RMSE={m['rmse']:.2f} MAE={m['mae']:.2f} "
          f"MASE(1passo)={m['mase_naive1']:.4f} MASE(sazonal)={m['mase_sazonal']:.4f}")
    if "custo_total" in m:
        print(f"Custo total (n_horas_custo={m['n_incluida_custo']}): R$ {m['custo_total']:,.2f}")

    print("\n=== Comparação com SARIMAX SEM temperatura (mesmo recorte 2024-01-20+, do log) ===")
    print("SARIMAX sem temp: MAPE=5.6895%")
    print(f"SARIMAX com temp (limpo): MAPE={m['mape']:.4f}%")
    diff = m["mape"] - 5.6895
    print(f"Delta: {diff:+.4f}pp — {'temperatura NÃO ajuda (piora ou empata)' if diff >= -0.05 else 'temperatura ajuda'}")


if __name__ == "__main__":
    main()
