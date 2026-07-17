"""Sondagem de integridade temporal por subsistema, sobre o período completo
2015-2026 (todos os anos baixados concatenados). Apenas lista fatos —
não preenche, não interpola, não remove nada.

Saída: data/interim/temporal_probe.json
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
        df = pd.read_parquet(fpath, columns=["id_subsistema", "nom_subsistema", "din_instante"])
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    return full


def longest_contiguous_run(timestamps: pd.Series) -> dict:
    """timestamps: sorted unique pandas Timestamps (hourly grid assumption)."""
    ts = timestamps.sort_values().reset_index(drop=True)
    if len(ts) == 0:
        return {"tamanho_horas": 0, "inicio": None, "fim": None}
    diffs = ts.diff().dt.total_seconds().div(3600)
    diffs.iloc[0] = 1.0  # primeira linha é NaN por definição (sem anterior); não é uma quebra real
    # marca onde a sequência quebra (diff != 1 hora) e agrupa por trecho contíguo
    run_id = (diffs != 1.0).cumsum()
    groups = ts.groupby(run_id)
    best_len = 0
    best_start = best_end = None
    for _, g in groups:
        if len(g) > best_len:
            best_len = len(g)
            best_start = g.iloc[0]
            best_end = g.iloc[-1]
    return {
        "tamanho_horas": int(best_len),
        "inicio": str(best_start),
        "fim": str(best_end),
    }


def probe_subsystem(sub_id: str, df_sub: pd.DataFrame) -> dict:
    ts = df_sub["din_instante"]
    ts_sorted = ts.sort_values()
    primeiro = ts_sorted.iloc[0]
    ultimo = ts_sorted.iloc[-1]

    n_total = len(df_sub)
    n_ts_distintos = ts.nunique()
    n_duplicados = n_total - n_ts_distintos
    dup_detail = None
    if n_duplicados > 0:
        vc = ts.value_counts()
        dup_ts = vc[vc > 1]
        dup_detail = [
            {"din_instante": str(idx), "n_ocorrencias": int(cnt)}
            for idx, cnt in dup_ts.sort_index().items()
        ]

    horas_esperadas = int((ultimo - primeiro).total_seconds() // 3600) + 1
    horas_observadas = n_ts_distintos

    # dias sem exatamente 24 registros (contagem de timestamps distintos por dia)
    # inclui dias 100% ausentes (0 registros), que não apareceriam num value_counts simples
    dia = ts.dt.date
    contagem_por_dia = dia.value_counts().sort_index()
    calendario_completo = pd.date_range(primeiro.normalize(), ultimo.normalize(), freq="D").date
    contagem_por_dia = contagem_por_dia.reindex(calendario_completo, fill_value=0)
    dias_irregulares = contagem_por_dia[contagem_por_dia != 24]
    dias_irregulares_list = [
        {"dia": str(d), "n_registros": int(c)} for d, c in dias_irregulares.items()
    ]

    maior_sequencia = longest_contiguous_run(ts.drop_duplicates())

    return {
        "id_subsistema": sub_id,
        "n_registros_total": int(n_total),
        "primeiro_din_instante": str(primeiro),
        "ultimo_din_instante": str(ultimo),
        "timestamps_distintos": int(n_ts_distintos),
        "timestamps_duplicados_qtd_linhas_extras": int(n_duplicados),
        "duplicados_detalhe": dup_detail,
        "horas_esperadas_no_periodo": horas_esperadas,
        "horas_observadas_timestamps_distintos": horas_observadas,
        "diferenca_esperado_menos_observado": horas_esperadas - horas_observadas,
        "n_dias_totais_no_periodo": int(len(contagem_por_dia)),
        "n_dias_com_exatamente_24_registros": int((contagem_por_dia == 24).sum()),
        "n_dias_irregulares": int(len(dias_irregulares_list)),
        "dias_irregulares": dias_irregulares_list,
        "maior_sequencia_contigua_sem_buraco": maior_sequencia,
    }


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    full = load_all()
    print(f"Total de linhas carregadas (todos os anos, todas as colunas de tempo): {len(full)}")

    resultados = []
    for sub_id, df_sub in full.groupby("id_subsistema"):
        r = probe_subsystem(sub_id, df_sub)
        resultados.append(r)
        print(
            f"--- {sub_id} --- registros={r['n_registros_total']} "
            f"periodo={r['primeiro_din_instante']} a {r['ultimo_din_instante']} "
            f"dup_linhas={r['timestamps_duplicados_qtd_linhas_extras']} "
            f"horas_esp={r['horas_esperadas_no_periodo']} horas_obs={r['horas_observadas_timestamps_distintos']} "
            f"dias_irregulares={r['n_dias_irregulares']} "
            f"maior_seq_h={r['maior_sequencia_contigua_sem_buraco']['tamanho_horas']}"
        )

    out_path = INTERIM_DIR / "temporal_probe.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False, default=str)
    print("Salvo em", out_path)


if __name__ == "__main__":
    main()
