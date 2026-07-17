"""Sondagem de esquema: para cada ano, reporta colunas, dtypes, n linhas,
e verifica (sem corrigir) divergências contra o dicionário de dados v1.2.

Fato observado no primeiro passe: val_cargaenergiahomwmed vem como STRING
(não FLOAT) nos arquivos de 2015-2024, e como float64 apenas em 2025-2026.
Por isso a checagem de nulo/negativo/zero trata ambos os casos sem alterar
os dados: para colunas string, tenta parse numérico apenas para fins de
contagem, sem escrever nada de volta em data/raw.

Saída: data/interim/schema_probe.json
"""
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
ANOS = list(range(2015, 2027))

EXPECTED_COLUMNS = {
    "id_subsistema": "object",
    "nom_subsistema": "object",
    "din_instante": "datetime64[ns]",
    "val_cargaenergiahomwmed": "float",
}


def probe_year(ano: int) -> dict:
    fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
    if not fpath.exists():
        return {"ano": ano, "status": "arquivo_ausente"}

    df = pd.read_parquet(fpath)

    result = {
        "ano": ano,
        "status": "ok",
        "n_linhas": int(len(df)),
        "colunas_presentes": list(df.columns),
        "dtypes_brutos": {c: str(t) for c, t in df.dtypes.items()},
        "colunas_divergem_do_esquema": sorted(
            set(df.columns) ^ set(EXPECTED_COLUMNS.keys())
        ),
    }

    # nulos por coluna declarada como not-null (NaN real, via isna)
    nulos = {}
    for col in EXPECTED_COLUMNS:
        if col in df.columns:
            nulos[col] = int(df[col].isna().sum())
        else:
            nulos[col] = "coluna_ausente"
    result["nulos_nan_por_coluna"] = nulos

    if "val_cargaenergiahomwmed" in df.columns:
        val_raw = df["val_cargaenergiahomwmed"]
        val_dtype = str(val_raw.dtype)
        result["val_dtype_real"] = val_dtype
        result["val_diverge_do_esquema_float"] = val_dtype not in ("float64", "float32")

        if pd.api.types.is_numeric_dtype(val_raw):
            val_num = val_raw
            result["val_strings_vazias"] = 0
            result["val_nao_parseavel_como_numero"] = 0
        else:
            s = val_raw.astype(str)
            n_vazia = int((s.str.strip() == "").sum())
            val_num = pd.to_numeric(val_raw, errors="coerce")
            n_nao_parseavel = int(val_num.isna().sum() - int(val_raw.isna().sum()) - n_vazia)
            result["val_strings_vazias"] = n_vazia
            result["val_nao_parseavel_como_numero"] = max(n_nao_parseavel, 0)

        val_num_valid = val_num.dropna()
        result["val_negativos"] = int((val_num_valid < 0).sum())
        result["val_zeros"] = int((val_num_valid == 0).sum())
        result["val_min_entre_parseaveis"] = float(val_num_valid.min()) if len(val_num_valid) else None
        result["val_max_entre_parseaveis"] = float(val_num_valid.max()) if len(val_num_valid) else None
    else:
        for k in ("val_negativos", "val_zeros", "val_dtype_real"):
            result[k] = "coluna_ausente"

    if "id_subsistema" in df.columns:
        result["id_subsistema_valores_distintos"] = sorted(
            str(x) for x in df["id_subsistema"].dropna().unique().tolist()
        )
        result["id_subsistema_n_distintos"] = int(df["id_subsistema"].nunique(dropna=True))
        lens = df["id_subsistema"].dropna().astype(str).str.len()
        result["id_subsistema_comprimento_min_max"] = [int(lens.min()), int(lens.max())] if len(lens) else None

    if "nom_subsistema" in df.columns:
        result["nom_subsistema_valores_distintos"] = sorted(
            str(x) for x in df["nom_subsistema"].dropna().unique().tolist()
        )
        lens = df["nom_subsistema"].dropna().astype(str).str.len()
        result["nom_subsistema_comprimento_min_max"] = [int(lens.min()), int(lens.max())] if len(lens) else None

    if "id_subsistema" in df.columns and "nom_subsistema" in df.columns:
        mapping = (
            df[["id_subsistema", "nom_subsistema"]]
            .drop_duplicates()
            .sort_values("id_subsistema")
        )
        result["mapeamento_id_para_nome"] = mapping.astype(str).to_dict(orient="records")

    return result


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    all_results = []
    for ano in ANOS:
        r = probe_year(ano)
        all_results.append(r)
        print(f"--- {ano} --- n_linhas={r.get('n_linhas')} dtype_val={r.get('val_dtype_real')} "
              f"vazias={r.get('val_strings_vazias')} nao_parseavel={r.get('val_nao_parseavel_como_numero')} "
              f"negativos={r.get('val_negativos')} zeros={r.get('val_zeros')} "
              f"ids={r.get('id_subsistema_valores_distintos')}")

    out_path = INTERIM_DIR / "schema_probe.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print("Salvo em", out_path)


if __name__ == "__main__":
    main()
