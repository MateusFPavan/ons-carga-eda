"""Checagens decisivas sobre o padrão nas viradas de DST + busca de zeros e
valores baixos em todo o período + análise de separador/round-trip da coluna
string + continuidade em UTC para SE/CO.

Não corrige nada em data/raw/. Apenas lê e reporta.
"""
import json
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
ANOS = list(range(2015, 2027))

DATAS_INICIO_DST = ["2015-10-18", "2016-10-16", "2017-10-15", "2018-11-04"]
DATAS_FIM_DST_SABADO = ["2015-02-21", "2016-02-20", "2017-02-18", "2018-02-17", "2019-02-16"]
DATAS_FIM_DST_DOMINGO = ["2015-02-22", "2016-02-21", "2017-02-19", "2018-02-18", "2019-02-17"]
TODAS_DATAS_VIRADA = set(DATAS_INICIO_DST + DATAS_FIM_DST_SABADO + DATAS_FIM_DST_DOMINGO)


def load_all() -> pd.DataFrame:
    frames = []
    for ano in ANOS:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        if not fpath.exists():
            continue
        df = pd.read_parquet(
            fpath, columns=["id_subsistema", "din_instante", "val_cargaenergiahomwmed"]
        )
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        df["ano_arquivo"] = ano
        df["val_raw_str"] = df["val_cargaenergiahomwmed"].astype(str)
        df["val_num"] = pd.to_numeric(df["val_cargaenergiahomwmed"], errors="coerce")
        df["val_dtype_original"] = str(df["val_cargaenergiahomwmed"].dtype)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def check_3_zeros_e_baixos(full: pd.DataFrame):
    print("\n=== TASK 3: zeros e valores abaixo de 10% da mediana, por subsistema ===")
    resultados = []
    for sub_id, df_sub in full.groupby("id_subsistema"):
        valid = df_sub.dropna(subset=["val_num"])
        mediana = valid["val_num"].median()
        limiar = 0.10 * mediana

        zeros = valid[valid["val_num"] == 0]
        baixos = valid[(valid["val_num"] > 0) & (valid["val_num"] < limiar)]

        for _, row in zeros.iterrows():
            resultados.append({
                "id_subsistema": sub_id, "din_instante": str(row["din_instante"]),
                "valor": float(row["val_num"]), "categoria": "zero",
                "coincide_com_data_de_virada": str(row["din_instante"].date()) in TODAS_DATAS_VIRADA,
            })
        for _, row in baixos.iterrows():
            resultados.append({
                "id_subsistema": sub_id, "din_instante": str(row["din_instante"]),
                "valor": float(row["val_num"]), "categoria": "abaixo_10pct_mediana",
                "coincide_com_data_de_virada": str(row["din_instante"].date()) in TODAS_DATAS_VIRADA,
            })
        print(f"{sub_id}: mediana={mediana:.2f} limiar_10pct={limiar:.2f} n_zeros={len(zeros)} n_baixos(excl.zero)={len(baixos)}")

    with open(INTERIM_DIR / "zeros_e_baixos.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)
    print(f"Total de ocorrências (zero + baixo): {len(resultados)}. Salvo em data/interim/zeros_e_baixos.json")
    for r in resultados:
        print(r)
    return resultados


def check_4_string_e_roundtrip(full: pd.DataFrame):
    print("\n=== TASK 4: separador decimal, caracteres distintos, round-trip, strings vazias ===")
    string_years_df = full[full["val_dtype_original"].isin(["str", "object"])]
    all_chars = set()
    for s in string_years_df["val_raw_str"]:
        all_chars.update(set(s))
    print("Caracteres distintos observados na coluna (anos string):", sorted(all_chars))

    # round-trip exato: string original vs str(float(string original))
    def try_roundtrip(s):
        if s.strip() == "":
            return None  # vazio, tratado separado
        try:
            f = float(s)
        except ValueError:
            return "nao_parseavel"
        return "match" if str(f) == s else "mismatch"

    string_years_df = string_years_df.copy()
    string_years_df["roundtrip_status"] = string_years_df["val_raw_str"].apply(try_roundtrip)
    contagem_roundtrip = string_years_df["roundtrip_status"].value_counts(dropna=False)
    print("\nContagem round-trip exato (str(float(x)) == x):")
    print(contagem_roundtrip.to_string())

    # amostra de mismatches
    mismatches = string_years_df[string_years_df["roundtrip_status"] == "mismatch"]
    print(f"\nTotal mismatches: {len(mismatches)} de {len(string_years_df)} linhas em anos-string")
    print("Amostra de 5 mismatches (original vs str(float(original))):")
    for _, row in mismatches.head(5).iterrows():
        print(f"  original={row['val_raw_str']!r}  str(float(x))={str(float(row['val_raw_str']))!r}")

    # round-trip numérico (via Decimal, checa perda de precisão além de formatação)
    from decimal import Decimal, InvalidOperation

    def numeric_roundtrip_ok(s):
        if s.strip() == "":
            return None
        try:
            d_original = Decimal(s)
        except InvalidOperation:
            return "nao_parseavel_decimal"
        f = float(s)
        d_via_float = Decimal(str(f))
        return "sem_perda_de_precisao" if d_original == d_via_float else "perda_de_precisao"

    string_years_df["numeric_roundtrip_status"] = string_years_df["val_raw_str"].apply(numeric_roundtrip_ok)
    contagem_numeric = string_years_df["numeric_roundtrip_status"].value_counts(dropna=False)
    print("\nContagem round-trip numérico (Decimal original == Decimal(str(float(original)))):")
    print(contagem_numeric.to_string())

    perda = string_years_df[string_years_df["numeric_roundtrip_status"] == "perda_de_precisao"]
    print(f"\nLinhas com perda de precisão numérica real: {len(perda)}")
    if len(perda):
        print(perda[["id_subsistema", "din_instante", "val_raw_str"]].head(10).to_string())

    # strings vazias: lista completa
    vazias = full[full["val_raw_str"].str.strip() == ""]
    vazias_list = vazias[["id_subsistema", "din_instante", "ano_arquivo"]].copy()
    vazias_list["din_instante"] = vazias_list["din_instante"].astype(str)
    vazias_records = vazias_list.to_dict(orient="records")
    print(f"\nTotal de strings vazias: {len(vazias_records)}")
    with open(INTERIM_DIR / "strings_vazias.json", "w", encoding="utf-8") as f:
        json.dump(vazias_records, f, indent=2, ensure_ascii=False)
    for r in vazias_records:
        print(r)

    return {
        "caracteres_distintos": sorted(all_chars),
        "roundtrip_exato": contagem_roundtrip.to_dict(),
        "roundtrip_numerico": contagem_numeric.to_dict(),
        "n_strings_vazias": len(vazias_records),
    }


def check_5_utc_continuidade(full: pd.DataFrame):
    print("\n=== TASK 5: continuidade em UTC (America/Sao_Paulo com DST histórico), SE/CO ===")
    seco = full[full["id_subsistema"] == "SE"].copy()
    seco = seco.dropna(subset=["din_instante"])
    tz = ZoneInfo("America/Sao_Paulo")

    def to_utc(naive_ts):
        localized = naive_ts.tz_localize(tz, ambiguous="raise", nonexistent="raise")
        return localized.tz_convert("UTC")

    resultados_localizacao = []
    utc_vals = []
    for ts in seco["din_instante"]:
        try:
            u = to_utc(ts)
            utc_vals.append(u)
            resultados_localizacao.append((ts, "ok", u))
        except Exception as e:
            utc_vals.append(pd.NaT)
            resultados_localizacao.append((ts, f"erro:{type(e).__name__}:{e}", None))

    seco["utc_status"] = [r[1] for r in resultados_localizacao]
    seco["din_instante_utc"] = utc_vals

    status_counts = seco["utc_status"].apply(lambda s: s if s == "ok" else s.split(":")[1]).value_counts()
    print("Status de localização/conversão para UTC:")
    print(status_counts.to_string())

    erros = seco[seco["utc_status"] != "ok"]
    print(f"\nTotal de timestamps que geraram erro/ambiguidade na conversão: {len(erros)}")
    if len(erros):
        print(erros[["din_instante", "utc_status"]].drop_duplicates().to_string())

    ok = seco[seco["utc_status"] == "ok"].copy()
    n_linhas_ok = len(ok)
    n_utc_distintos = ok["din_instante_utc"].nunique()
    n_duplicados_utc = n_linhas_ok - n_utc_distintos
    print(f"\nLinhas convertidas com sucesso: {n_linhas_ok}")
    print(f"Timestamps UTC distintos: {n_utc_distintos}")
    print(f"Diferença (duplicatas em UTC): {n_duplicados_utc}")

    ts_utc_sorted = ok["din_instante_utc"].drop_duplicates().sort_values().reset_index(drop=True)
    diffs = ts_utc_sorted.diff().dt.total_seconds().div(3600)
    diffs.iloc[0] = 1.0
    quebras = diffs[diffs != 1.0]
    print(f"\nQuebras na sequência UTC (diff != 1h): {len(quebras)}")
    if len(quebras):
        for idx in quebras.index:
            print(f"  entre {ts_utc_sorted.iloc[idx-1]} e {ts_utc_sorted.iloc[idx]} (diff={diffs.iloc[idx]}h)")

    resultado = {
        "n_linhas_seco_total": int(len(seco)),
        "n_linhas_convertidas_ok": int(n_linhas_ok),
        "n_erros_localizacao": int(len(erros)),
        "detalhe_erros": erros[["din_instante", "utc_status"]].drop_duplicates().astype(str).to_dict(orient="records") if len(erros) else [],
        "n_timestamps_utc_distintos": int(n_utc_distintos),
        "n_duplicatas_utc": int(n_duplicados_utc),
        "n_quebras_sequencia_utc": int(len(quebras)),
        "detalhe_quebras": [
            {"de": str(ts_utc_sorted.iloc[idx - 1]), "para": str(ts_utc_sorted.iloc[idx]), "diff_horas": float(diffs.iloc[idx])}
            for idx in quebras.index
        ],
    }
    with open(INTERIM_DIR / "utc_continuidade.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    return resultado


def main():
    full = load_all()
    print(f"Total linhas carregadas: {len(full)}")

    check_3_zeros_e_baixos(full)
    check_4_string_e_roundtrip(full)
    check_5_utc_continuidade(full)


if __name__ == "__main__":
    main()
