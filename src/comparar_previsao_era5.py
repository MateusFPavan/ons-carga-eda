"""Compara temperature_2m_previous_day1 (previsão 24h antes) contra ERA5 (reanálise),
por cidade e agregado. Não corrige, não decide — só calcula e reporta.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TEMP_DIR = RAW_DIR / "temperatura"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"

CIDADES = ["Sao_Paulo", "Rio_de_Janeiro", "Belo_Horizonte", "Brasilia", "Goiania"]


def carregar(cidade):
    era5 = json.loads((TEMP_DIR / f"era5_temperature_2m_{cidade}_2024_2025.json").read_text(encoding="utf-8"))
    prev = json.loads((TEMP_DIR / f"openmeteo_previous_day1_{cidade}_2024_2025.json").read_text(encoding="utf-8"))

    df_era5 = pd.DataFrame({"time": era5["hourly"]["time"], "era5": era5["hourly"]["temperature_2m"]})
    df_prev = pd.DataFrame({"time": prev["hourly"]["time"], "previsao": prev["hourly"]["temperature_2m_previous_day1"]})

    meta = {
        "era5_timezone": era5.get("timezone"), "era5_utc_offset_seconds": era5.get("utc_offset_seconds"),
        "prev_timezone": prev.get("timezone"), "prev_utc_offset_seconds": prev.get("utc_offset_seconds"),
        "era5_lat_grade": era5.get("latitude"), "era5_lon_grade": era5.get("longitude"),
        "prev_lat_grade": prev.get("latitude"), "prev_lon_grade": prev.get("longitude"),
        "era5_primeiro_ts": era5["hourly"]["time"][0], "era5_ultimo_ts": era5["hourly"]["time"][-1],
        "prev_primeiro_ts": prev["hourly"]["time"][0], "prev_ultimo_ts": prev["hourly"]["time"][-1],
        "era5_n_linhas": len(df_era5), "prev_n_linhas": len(df_prev),
    }
    return df_era5, df_prev, meta


def metricas(erro: pd.Series) -> dict:
    return {
        "n": int(len(erro)),
        "mae": float(erro.abs().mean()) if len(erro) else None,
        "rmse": float(np.sqrt((erro ** 2).mean())) if len(erro) else None,
        "vies": float(erro.mean()) if len(erro) else None,
    }


def main():
    resultado_por_cidade = {}
    todas_linhas = []

    for cidade in CIDADES:
        df_era5, df_prev, meta = carregar(cidade)
        print(f"\n=== {cidade} ===")
        print(json.dumps(meta, indent=2, ensure_ascii=False))

        merged = pd.merge(df_era5, df_prev, on="time", how="outer", indicator=True)
        n_so_era5 = int((merged["_merge"] == "left_only").sum())
        n_so_prev = int((merged["_merge"] == "right_only").sum())
        n_ambos_timestamp = int((merged["_merge"] == "both").sum())
        print(f"timestamps só em ERA5: {n_so_era5}, só em previsão: {n_so_prev}, em ambos: {n_ambos_timestamp}")

        merged["era5"] = pd.to_numeric(merged["era5"], errors="coerce")
        merged["previsao"] = pd.to_numeric(merged["previsao"], errors="coerce")

        n_nulo_era5 = int(merged["era5"].isna().sum())
        n_nulo_prev = int(merged["previsao"].isna().sum())

        comparavel = merged.dropna(subset=["era5", "previsao"]).copy()
        n_comparavel = len(comparavel)
        n_descartado = len(merged) - n_comparavel

        comparavel["erro"] = comparavel["previsao"] - comparavel["era5"]
        comparavel["hora"] = pd.to_datetime(comparavel["time"]).dt.hour
        comparavel["cidade"] = cidade

        m_geral = metricas(comparavel["erro"])

        p95 = comparavel["era5"].quantile(0.95)
        p5 = comparavel["era5"].quantile(0.05)
        subset_p95 = comparavel[comparavel["era5"] >= p95]
        subset_p5 = comparavel[comparavel["era5"] <= p5]
        m_p95 = metricas(subset_p95["erro"])
        m_p5 = metricas(subset_p5["erro"])

        mae_por_hora = comparavel.groupby("hora")["erro"].apply(lambda s: float(s.abs().mean())).to_dict()

        resultado_por_cidade[cidade] = {
            "meta": meta,
            "n_timestamps_so_era5": n_so_era5,
            "n_timestamps_so_previsao": n_so_prev,
            "n_timestamps_em_ambos": n_ambos_timestamp,
            "n_nulo_era5": n_nulo_era5,
            "n_nulo_previsao": n_nulo_prev,
            "n_horas_comparaveis": n_comparavel,
            "n_horas_descartadas": n_descartado,
            "limiar_p95_era5_C": float(p95),
            "limiar_p5_era5_C": float(p5),
            "metricas_geral": m_geral,
            "metricas_p95_dias_quentes": m_p95,
            "metricas_p5_dias_frios": m_p5,
            "mae_por_hora": mae_por_hora,
        }
        print(f"comparáveis={n_comparavel} descartadas={n_descartado} MAE={m_geral['mae']:.4f} RMSE={m_geral['rmse']:.4f} vies={m_geral['vies']:.4f}")
        print(f"p95(>={p95:.2f}C) n={m_p95['n']} MAE={m_p95['mae']:.4f} | p5(<={p5:.2f}C) n={m_p5['n']} MAE={m_p5['mae']:.4f}")

        todas_linhas.append(comparavel[["time", "hora", "cidade", "era5", "previsao", "erro"]])

    # agregado (todas as cidades juntas)
    agregado_df = pd.concat(todas_linhas, ignore_index=True)
    m_agregado = metricas(agregado_df["erro"])
    p95_agg = agregado_df["era5"].quantile(0.95)
    p5_agg = agregado_df["era5"].quantile(0.05)
    m_agg_p95 = metricas(agregado_df[agregado_df["era5"] >= p95_agg]["erro"])
    m_agg_p5 = metricas(agregado_df[agregado_df["era5"] <= p5_agg]["erro"])
    mae_por_hora_agg = agregado_df.groupby("hora")["erro"].apply(lambda s: float(s.abs().mean())).to_dict()

    print("\n=== AGREGADO (5 cidades) ===")
    print(f"n_total_comparavel={m_agregado['n']} MAE={m_agregado['mae']:.4f} RMSE={m_agregado['rmse']:.4f} vies={m_agregado['vies']:.4f}")
    print(f"p95(>={p95_agg:.2f}C) n={m_agg_p95['n']} MAE={m_agg_p95['mae']:.4f} | p5(<={p5_agg:.2f}C) n={m_agg_p5['n']} MAE={m_agg_p5['mae']:.4f}")

    resultado_final = {
        "por_cidade": resultado_por_cidade,
        "agregado": {
            "metricas_geral": m_agregado,
            "limiar_p95_era5_C": float(p95_agg),
            "limiar_p5_era5_C": float(p5_agg),
            "metricas_p95_dias_quentes": m_agg_p95,
            "metricas_p5_dias_frios": m_agg_p5,
            "mae_por_hora": mae_por_hora_agg,
        },
    }
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    with open(INTERIM_DIR / "comparacao_previsao_era5.json", "w", encoding="utf-8") as f:
        json.dump(resultado_final, f, indent=2, ensure_ascii=False, default=str)
    print("\nSalvo em data/interim/comparacao_previsao_era5.json")


if __name__ == "__main__":
    main()
