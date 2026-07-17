"""Extrai a estação A701 (São Paulo - Mirante) do ZIP anual do INMET, converte para
America/Sao_Paulo, trata 9999/vazio como ausente, e compara contra ERA5 no mesmo
período. Não altera o ZIP nem cria nenhum arquivo fora de data/raw e data/interim.
"""
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TEMP_DIR = RAW_DIR / "temperatura"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
ZIP_PATH = TEMP_DIR / "inmet_dadoshistoricos_2024.zip"


def encontrar_membro_a701(zf: zipfile.ZipFile) -> str:
    candidatos = [n for n in zf.namelist() if "A701" in n.upper()]
    return candidatos[0] if candidatos else None


def ler_estacao(zf: zipfile.ZipFile, membro: str) -> pd.DataFrame:
    with zf.open(membro) as f:
        raw_bytes = f.read()
    texto = raw_bytes.decode("latin-1")
    linhas = texto.splitlines()
    # cabeçalho de metadados do INMET vem nas primeiras ~8 linhas; a linha de colunas
    # é a primeira que começa com "Data"
    idx_cabecalho = next(i for i, l in enumerate(linhas) if l.startswith("Data"))
    cabecalho_meta = linhas[:idx_cabecalho]
    from io import StringIO
    df = pd.read_csv(StringIO("\n".join(linhas[idx_cabecalho:])), sep=";", decimal=",", encoding="latin-1")
    return df, cabecalho_meta


def main():
    if not ZIP_PATH.exists():
        print("ZIP do INMET não encontrado — nada a fazer.")
        return

    with zipfile.ZipFile(ZIP_PATH) as zf:
        membro = encontrar_membro_a701(zf)
        print("Membro A701 encontrado no ZIP:", membro)
        if membro is None:
            print("Nenhum arquivo A701 encontrado no ZIP.")
            return
        df, meta = ler_estacao(zf, membro)

    print("Metadados do cabeçalho do arquivo INMET:")
    for l in meta:
        print(" ", l)
    print("Colunas:", list(df.columns))
    print("N linhas brutas:", len(df))
    print(df.head(3).to_string())

    # coluna de data e hora, e coluna de temperatura instantânea
    col_data = [c for c in df.columns if c.strip().upper() == "DATA"][0]
    col_hora = [c for c in df.columns if "HORA" in c.strip().upper()][0]
    col_temp = [c for c in df.columns if "TEMPERATURA DO AR" in c.upper() and "BULBO SECO" in c.upper()]
    if not col_temp:
        col_temp = [c for c in df.columns if "TEMPERATURA DO AR" in c.upper()]
    col_temp = col_temp[0]
    print("Coluna de data:", col_data, "| hora:", col_hora, "| temperatura:", col_temp)

    df["hora_str"] = df[col_hora].astype(str).str.replace(" UTC", "", regex=False).str.zfill(4)
    df["hora_fmt"] = df["hora_str"].str[:2] + ":" + df["hora_str"].str[2:]
    df["din_utc_naive"] = pd.to_datetime(df[col_data].astype(str) + " " + df["hora_fmt"], format="%Y/%m/%d %H:%M", errors="coerce")
    if df["din_utc_naive"].isna().all():
        df["din_utc_naive"] = pd.to_datetime(df[col_data].astype(str) + " " + df["hora_fmt"], format="%Y-%m-%d %H:%M", errors="coerce")

    n_datas_invalidas = int(df["din_utc_naive"].isna().sum())
    print("Linhas com data/hora não parseável:", n_datas_invalidas)

    df["din_utc"] = df["din_utc_naive"].dt.tz_localize("UTC")
    df["din_local"] = df["din_utc"].dt.tz_convert("America/Sao_Paulo")

    temp_raw = df[col_temp].astype(str).str.strip()
    n_9999 = int((temp_raw == "9999").sum() + (temp_raw == "9999,0").sum() + (temp_raw == "-9999").sum())
    temp_num = pd.to_numeric(df[col_temp], errors="coerce")
    temp_num = temp_num.mask(temp_num.abs() >= 9999, np.nan)
    n_ausente_total = int(temp_num.isna().sum())

    print(f"Linhas com 9999 (falha declarada): {n_9999}")
    print(f"Linhas ausentes no total (9999 + vazio + não-parseável): {n_ausente_total} de {len(df)}")

    obs = pd.DataFrame({"din_local": df["din_local"], "temp_inmet": temp_num}).dropna(subset=["din_local"])
    obs["time"] = obs["din_local"].dt.strftime("%Y-%m-%dT%H:%M")
    obs = obs.groupby("time", as_index=False)["temp_inmet"].mean()

    era5 = json.loads((TEMP_DIR / "era5_temperature_2m_Sao_Paulo_2024_2025.json").read_text(encoding="utf-8"))
    df_era5 = pd.DataFrame({"time": era5["hourly"]["time"], "era5": era5["hourly"]["temperature_2m"]})
    df_era5_2024 = df_era5[df_era5["time"] < "2025-01-01"]

    merged = pd.merge(df_era5_2024, obs, on="time", how="inner")
    merged["era5"] = pd.to_numeric(merged["era5"], errors="coerce")
    comparavel = merged.dropna(subset=["era5", "temp_inmet"])
    n_comparavel = len(comparavel)
    n_descartado = len(merged) - n_comparavel

    erro = comparavel["temp_inmet"] - comparavel["era5"]
    mae = float(erro.abs().mean())
    rmse = float(np.sqrt((erro ** 2).mean()))
    vies = float(erro.mean())

    print(f"\nHoras com timestamp comum ERA5 x INMET (2024): {len(merged)}")
    print(f"Horas comparáveis (sem nulo em nenhum lado): {n_comparavel}")
    print(f"Horas descartadas: {n_descartado}")
    print(f"MAE(ERA5, INMET A701)={mae:.4f}  RMSE={rmse:.4f}  vies(inmet-era5)={vies:.4f}")

    resultado = {
        "membro_zip": membro,
        "n_linhas_brutas_estacao": len(df),
        "n_datas_invalidas": n_datas_invalidas,
        "n_9999_declarado": n_9999,
        "n_ausente_total_temperatura": n_ausente_total,
        "n_timestamps_comuns_era5_inmet_2024": len(merged),
        "n_horas_comparaveis": n_comparavel,
        "n_horas_descartadas": n_descartado,
        "mae_era5_vs_inmet": mae,
        "rmse_era5_vs_inmet": rmse,
        "vies_inmet_menos_era5": vies,
    }
    with open(INTERIM_DIR / "comparacao_inmet_era5.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    print("\nSalvo em data/interim/comparacao_inmet_era5.json")


if __name__ == "__main__":
    main()
