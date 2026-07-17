"""Sondagem descritiva bruta de val_cargaenergiahomwmed por subsistema.

val_cargaenergiahomwmed vem como string em 2015-2024 (ver src/probe_schema.py).
Para calcular estatísticas é preciso parsear para número; os poucos valores
não-parseáveis (strings vazias, ver schema_probe.json) são excluídos do
cálculo e a contagem de exclusão é reportada — não são preenchidos nem
interpolados.

Saída: data/interim/descriptive_probe.json
"""
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
ANOS = list(range(2015, 2027))


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
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    full["val_num"] = pd.to_numeric(full["val_cargaenergiahomwmed"], errors="coerce")
    return full


def probe_subsystem(sub_id: str, df_sub: pd.DataFrame) -> dict:
    n_total = len(df_sub)
    valid = df_sub.dropna(subset=["val_num"])
    n_excluidos = n_total - len(valid)
    v = valid["val_num"]

    idx_max = v.idxmax()
    idx_min = v.idxmin()

    return {
        "id_subsistema": sub_id,
        "n_registros_total": int(n_total),
        "n_excluidos_valor_nao_parseavel": int(n_excluidos),
        "n_usados_no_calculo": int(len(v)),
        "min": float(v.min()),
        "max": float(v.max()),
        "media": float(v.mean()),
        "mediana": float(v.median()),
        "desvio_padrao": float(v.std()),
        "q1_25": float(v.quantile(0.25)),
        "q3_75": float(v.quantile(0.75)),
        "din_instante_do_maximo": str(df_sub.loc[idx_max, "din_instante"]),
        "din_instante_do_minimo": str(df_sub.loc[idx_min, "din_instante"]),
    }


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    full = load_all()

    resultados = []
    for sub_id, df_sub in full.groupby("id_subsistema"):
        r = probe_subsystem(sub_id, df_sub)
        resultados.append(r)
        print(
            f"--- {sub_id} --- n={r['n_usados_no_calculo']} excluidos={r['n_excluidos_valor_nao_parseavel']} "
            f"min={r['min']:.2f} max={r['max']:.2f} media={r['media']:.2f} mediana={r['mediana']:.2f} "
            f"std={r['desvio_padrao']:.2f} q1={r['q1_25']:.2f} q3={r['q3_75']:.2f} "
            f"max_em={r['din_instante_do_maximo']} min_em={r['din_instante_do_minimo']}"
        )

    out_path = INTERIM_DIR / "descriptive_probe.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False, default=str)
    print("Salvo em", out_path)


if __name__ == "__main__":
    main()
