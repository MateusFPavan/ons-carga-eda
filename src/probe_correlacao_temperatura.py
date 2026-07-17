"""Parte C: correlação de temperatura entre as 5 capitais do SE/CO (previous_day1,
jan/2024-dez/2025) e correlação de cada cidade com a carga horária do SE/CO
(2024-01-20 em diante). Diagnóstico de redundância — não seleciona feature.
"""
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TEMP_DIR = RAW_DIR / "temperatura"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"

CIDADES = ["Sao_Paulo", "Rio_de_Janeiro", "Belo_Horizonte", "Brasilia", "Goiania"]


def carregar_previous_day1(cidade: str) -> pd.Series:
    fpath = TEMP_DIR / f"openmeteo_previous_day1_{cidade}_2024_2025.json"
    j = json.loads(fpath.read_text(encoding="utf-8"))
    s = pd.Series(j["hourly"]["temperature_2m_previous_day1"], index=pd.to_datetime(j["hourly"]["time"]))
    return pd.to_numeric(s, errors="coerce")


def carregar_carga_se_periodo(inicio: str, fim: str) -> pd.Series:
    frames = []
    for ano in [2024, 2025]:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        if not fpath.exists():
            continue
        df = pd.read_parquet(fpath, columns=["id_subsistema", "din_instante", "val_cargaenergiahomwmed"])
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        df = df[df["id_subsistema"] == "SE"].copy()
        df["val_num"] = pd.to_numeric(df["val_cargaenergiahomwmed"], errors="coerce")
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    s = full.set_index("din_instante")["val_num"]
    return s[(s.index >= inicio) & (s.index <= fim)]


def main():
    print("Carregando previous_day1 das 5 cidades...")
    series = {c: carregar_previous_day1(c) for c in CIDADES}
    df_temp = pd.DataFrame(series)
    print(f"Linhas totais no índice (união): {len(df_temp)}")

    print("\n=== C1: matriz de correlação entre as 5 cidades (previous_day1) ===")
    matriz_corr = df_temp.corr()
    print(matriz_corr.round(4).to_string())

    print("\n=== C3: cobertura simultânea ===")
    n_todas_5 = int(df_temp.dropna(how="any").shape[0])
    n_pelo_menos_1 = int(df_temp.dropna(how="all").shape[0])
    n_total_grade = int(len(df_temp))
    print(f"Horas com dado nas 5 cidades simultaneamente: {n_todas_5}")
    print(f"Horas com dado em pelo menos 1 cidade: {n_pelo_menos_1}")
    print(f"Horas totais na grade (união de timestamps): {n_total_grade}")

    print("\n=== C2: correlação de cada cidade com a carga SE/CO (2024-01-20 em diante) ===")
    carga = carregar_carga_se_periodo("2024-01-20", "2025-12-31 23:00:00")
    print(f"Linhas de carga SE/CO no período: {len(carga)}")

    correlacoes_carga = {}
    n_horas_comparaveis = {}
    for cidade in CIDADES:
        temp_c = df_temp[cidade]
        temp_c = temp_c[(temp_c.index >= "2024-01-20") & (temp_c.index <= "2025-12-31 23:00:00")]
        comb = pd.DataFrame({"temp": temp_c, "carga": carga}).dropna()
        corr = float(comb["temp"].corr(comb["carga"])) if len(comb) > 1 else None
        correlacoes_carga[cidade] = corr
        n_horas_comparaveis[cidade] = int(len(comb))
        print(f"{cidade}: n_comparavel={len(comb)} correlacao_com_carga={corr:.4f}" if corr is not None else f"{cidade}: sem dado suficiente")

    resultado = {
        "matriz_correlacao_5_cidades": matriz_corr.round(6).to_dict(),
        "n_horas_5_cidades_simultaneo": n_todas_5,
        "n_horas_pelo_menos_1_cidade": n_pelo_menos_1,
        "n_horas_total_grade_uniao": n_total_grade,
        "correlacoes_com_carga_se": correlacoes_carga,
        "n_horas_comparaveis_com_carga": n_horas_comparaveis,
    }
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    with open(INTERIM_DIR / "probe_correlacao_temperatura.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    print("\nSalvo em data/interim/probe_correlacao_temperatura.json")


if __name__ == "__main__":
    main()
