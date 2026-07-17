"""Sondagem das 3 amostras de 2024 de custo de despacho: esquema observado vs.
declarado, granularidade temporal real, recorte por subsistema, unidade, estatísticas
descritivas, nulos/zeros/negativos. Não corrige, não decide — só reporta.
"""
import json
from pathlib import Path

import pandas as pd

CUSTO_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "custo"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"


def descrever_coluna_numerica(s: pd.Series) -> dict:
    valido = pd.to_numeric(s, errors="coerce")
    n_nulo_declarado = int(s.isna().sum())
    n_nao_parseavel = int(valido.isna().sum() - n_nulo_declarado)
    v = valido.dropna()
    if len(v) == 0:
        return {"n_validos": 0}
    return {
        "n_validos": int(len(v)),
        "n_nulo": n_nulo_declarado,
        "n_nao_parseavel_extra": max(n_nao_parseavel, 0),
        "n_negativos": int((v < 0).sum()),
        "n_zeros": int((v == 0).sum()),
        "min": float(v.min()),
        "max": float(v.max()),
        "media": float(v.mean()),
        "mediana": float(v.median()),
        "q1": float(v.quantile(0.25)),
        "q3": float(v.quantile(0.75)),
    }


def main():
    resultado = {}

    print("=" * 100)
    print("CMO SEMI-HORÁRIO 2024")
    print("=" * 100)
    df = pd.read_parquet(CUSTO_DIR / "cmo_semi_horario_2024.parquet")
    print("Colunas observadas:", list(df.columns))
    print("Dtypes:", dict(df.dtypes.astype(str)))
    print("N linhas:", len(df))
    print(df.head(10).to_string())

    ids = sorted(df["id_subsistema"].astype(str).unique().tolist()) if "id_subsistema" in df.columns else None
    print("id_subsistema distintos:", ids)
    if "nom_subsistema" in df.columns:
        mapa = df[["id_subsistema", "nom_subsistema"]].drop_duplicates().sort_values("id_subsistema")
        print(mapa.to_string())

    ts = pd.to_datetime(df["din_instante"]).sort_values().unique()
    ts = pd.Series(ts)
    diffs = ts.diff().dropna()
    print("Diferenças de tempo distintas entre timestamps consecutivos (segundos):", sorted(diffs.dt.total_seconds().unique().tolist())[:10])
    print("Primeiro instante:", ts.iloc[0], "| Último instante:", ts.iloc[-1])

    stats_cmo = descrever_coluna_numerica(df["val_cmo"]) if "val_cmo" in df.columns else None
    print("Estatísticas val_cmo:", json.dumps(stats_cmo, indent=2))

    resultado["cmo_semi_horario"] = {
        "colunas": list(df.columns), "dtypes": dict(df.dtypes.astype(str)),
        "n_linhas": int(len(df)), "id_subsistema_distintos": ids,
        "primeiro_instante": str(ts.iloc[0]), "ultimo_instante": str(ts.iloc[-1]),
        "diffs_segundos_distintos": sorted(diffs.dt.total_seconds().unique().tolist()),
        "estatisticas_val_cmo": stats_cmo,
    }

    print("\n" + "=" * 100)
    print("CMO SEMANAL 2024")
    print("=" * 100)
    df2 = pd.read_parquet(CUSTO_DIR / "cmo_semanal_2024.parquet")
    print("Colunas observadas:", list(df2.columns))
    print("Dtypes:", dict(df2.dtypes.astype(str)))
    print("N linhas:", len(df2))
    print(df2.head(10).to_string())

    ids2 = sorted(df2["id_subsistema"].astype(str).unique().tolist()) if "id_subsistema" in df2.columns else None
    print("id_subsistema distintos:", ids2)

    ts2 = pd.to_datetime(df2["din_instante"]).sort_values().unique()
    ts2 = pd.Series(ts2)
    diffs2 = ts2.diff().dropna()
    print("Diferenças de tempo distintas entre datas consecutivas (dias):", sorted((diffs2.dt.total_seconds() / 86400).unique().tolist())[:10])
    print("Primeira semana:", ts2.iloc[0], "| Última semana:", ts2.iloc[-1])

    stats_semanal = {}
    for col in ["val_cmomediasemanal", "val_cmoleve", "val_cmomedia", "val_cmopesada"]:
        if col in df2.columns:
            stats_semanal[col] = descrever_coluna_numerica(df2[col])
    print("Estatísticas colunas CMO semanal:", json.dumps(stats_semanal, indent=2))

    resultado["cmo_semanal"] = {
        "colunas": list(df2.columns), "dtypes": dict(df2.dtypes.astype(str)),
        "n_linhas": int(len(df2)), "id_subsistema_distintos": ids2,
        "primeiro_instante": str(ts2.iloc[0]), "ultimo_instante": str(ts2.iloc[-1]),
        "diffs_dias_distintos": sorted((diffs2.dt.total_seconds() / 86400).unique().tolist()),
        "estatisticas": stats_semanal,
    }

    print("\n" + "=" * 100)
    print("CVU USINA TÉRMICA 2024")
    print("=" * 100)
    df3 = pd.read_parquet(CUSTO_DIR / "cvu_usina_termica_2024.parquet")
    print("Colunas observadas:", list(df3.columns))
    print("Dtypes:", dict(df3.dtypes.astype(str)))
    print("N linhas:", len(df3))
    print(df3.head(10).to_string())

    ids3 = sorted(df3["id_subsistema"].astype(str).unique().tolist()) if "id_subsistema" in df3.columns else None
    print("id_subsistema distintos:", ids3)

    n_usinas = df3["nom_usina"].nunique() if "nom_usina" in df3.columns else None
    n_cod_usinas = df3["cod_usinaplanejamento"].nunique() if "cod_usinaplanejamento" in df3.columns else None
    print("N usinas distintas (nom_usina):", n_usinas)
    print("N códigos de usina distintos (cod_usinaplanejamento):", n_cod_usinas)

    if "num_revisao" in df3.columns:
        print("Valores distintos de num_revisao:", sorted(df3["num_revisao"].unique().tolist()))
    if "mes_referencia" in df3.columns:
        print("Valores distintos de mes_referencia:", sorted(df3["mes_referencia"].unique().tolist()))
    if "dat_iniciosemana" in df3.columns:
        semanas = sorted(df3["dat_iniciosemana"].astype(str).unique().tolist())
        print(f"N semanas distintas: {len(semanas)}. Primeira: {semanas[0]} Última: {semanas[-1]}")

    stats_cvu = descrever_coluna_numerica(df3["val_cvu"]) if "val_cvu" in df3.columns else None
    print("Estatísticas val_cvu:", json.dumps(stats_cvu, indent=2))

    resultado["cvu_usina_termica"] = {
        "colunas": list(df3.columns), "dtypes": dict(df3.dtypes.astype(str)),
        "n_linhas": int(len(df3)), "id_subsistema_distintos": ids3,
        "n_usinas_distintas": int(n_usinas) if n_usinas is not None else None,
        "n_codigos_usina_distintos": int(n_cod_usinas) if n_cod_usinas is not None else None,
        "valores_num_revisao": sorted(df3["num_revisao"].unique().tolist()) if "num_revisao" in df3.columns else None,
        "valores_mes_referencia": sorted(df3["mes_referencia"].unique().tolist()) if "mes_referencia" in df3.columns else None,
        "n_semanas_distintas": len(semanas) if "dat_iniciosemana" in df3.columns else None,
        "estatisticas_val_cvu": stats_cvu,
    }

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    with open(INTERIM_DIR / "probe_custo.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    print("\nSalvo em data/interim/probe_custo.json")


if __name__ == "__main__":
    main()
