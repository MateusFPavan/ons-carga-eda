"""Sondagem da hipótese de grade horária artificialmente regularizada nas viradas
de horário de verão (DST) brasileiro. Não corrige, não decide — só extrai e reporta.

Saída: data/interim/dst_dates.csv (tabela larga por data/hora, subsistemas em coluna)
       data/interim/dst_dates.json (mesma coisa em JSON, com val bruto e parseado)
"""
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
ANOS = list(range(2015, 2027))

# Datas de virada determinadas via zoneinfo (America/Sao_Paulo, IANA tzdata) — ver
# reports/01_dst_verificacao.md seção 1 para o script de derivação e cross-check.
DATAS_INICIO_DST = ["2015-10-18", "2016-10-16", "2017-10-15", "2018-11-04"]
DATAS_FIM_DST_SABADO = ["2015-02-21", "2016-02-20", "2017-02-18", "2018-02-17", "2019-02-16"]
DATAS_FIM_DST_DOMINGO = ["2015-02-22", "2016-02-21", "2017-02-19", "2018-02-18", "2019-02-17"]

TODAS_DATAS = sorted(set(DATAS_INICIO_DST + DATAS_FIM_DST_SABADO + DATAS_FIM_DST_DOMINGO))


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
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    return full


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    full = load_all()
    print(f"Total linhas carregadas: {len(full)}")

    mask = full["din_instante"].dt.date.astype(str).isin(TODAS_DATAS)
    subset = full.loc[mask].copy()
    subset = subset.sort_values(["din_instante", "id_subsistema"])
    print(f"Linhas nas {len(TODAS_DATAS)} datas de virada: {len(subset)}")

    subset.to_json(INTERIM_DIR / "dst_dates.json", orient="records", date_format="iso", indent=2, force_ascii=False)

    # tabela larga: din_instante x subsistema, valor bruto (string original)
    wide = subset.pivot_table(
        index="din_instante", columns="id_subsistema", values="val_raw_str", aggfunc=lambda x: "|".join(x)
    )
    wide.to_csv(INTERIM_DIR / "dst_dates_wide.csv", encoding="utf-8")
    print("Salvo data/interim/dst_dates.json e dst_dates_wide.csv")

    # contagem de linhas por (data, subsistema) para checagem rápida
    contagem = subset.groupby([subset["din_instante"].dt.date.astype(str), "id_subsistema"]).size().unstack(fill_value=0)
    print(contagem.to_string())
    contagem.to_csv(INTERIM_DIR / "dst_dates_contagem.csv", encoding="utf-8")


if __name__ == "__main__":
    main()
