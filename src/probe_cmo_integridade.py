"""Parte A: integridade das semi-horas do CMO Semi-Horário 2024 e verificação de
timezone (local vs UTC), antes de qualquer agregação. Não corrige, não decide.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CUSTO_DIR = RAW_DIR / "custo"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"


def carregar_carga_2024():
    fpath = RAW_DIR / "CURVA_CARGA_2024.parquet"
    df = pd.read_parquet(fpath)
    df["id_subsistema"] = df["id_subsistema"].astype(str)
    df["val_num"] = pd.to_numeric(df["val_cargaenergiahomwmed"], errors="coerce")
    return df


def a1_a2_integridade_semi_horas(cmo: pd.DataFrame) -> dict:
    resultado = {}
    for sub_id, g in cmo.groupby("id_subsistema"):
        g = g.copy()
        g["hora_local"] = g["din_instante"].dt.floor("h")
        contagem = g.groupby("hora_local").size()

        n_2 = int((contagem == 2).sum())
        n_1 = int((contagem == 1).sum())
        n_mais_2 = int((contagem > 2).sum())

        horas_com_1 = contagem[contagem == 1].index
        detalhe_1 = []
        for h in horas_com_1:
            linha = g[g["hora_local"] == h].iloc[0]
            detalhe_1.append({"hora": str(h), "din_instante_presente": str(linha["din_instante"]), "val_cmo": float(linha["val_cmo"])})

        detalhe_mais_2 = []
        if n_mais_2 > 0:
            horas_mais_2 = contagem[contagem > 2].index
            for h in horas_mais_2:
                linhas = g[g["hora_local"] == h][["din_instante", "val_cmo"]].astype(str).to_dict(orient="records")
                detalhe_mais_2.append({"hora": str(h), "linhas": linhas})

        resultado[sub_id] = {
            "n_horas_com_2_semihoras": n_2,
            "n_horas_com_1_semihora": n_1,
            "n_horas_com_mais_de_2": n_mais_2,
            "n_horas_total_com_dado": int(len(contagem)),
            "detalhe_horas_com_1": detalhe_1,
            "detalhe_horas_com_mais_de_2": detalhe_mais_2,
        }

    se = cmo[cmo["id_subsistema"] == "SE"].copy()
    se["hora_local"] = se["din_instante"].dt.floor("h")
    horas_presentes = set(se["hora_local"].unique())
    ano = se["din_instante"].min().year
    grade_completa_horas = pd.date_range(f"{ano}-01-01", f"{ano}-12-31 23:00", freq="h")
    horas_ausentes = sorted(set(grade_completa_horas) - horas_presentes)
    resultado["SE"]["n_horas_com_0_semihoras"] = len(horas_ausentes)
    resultado["SE"]["n_horas_grade_completa_esperada"] = len(grade_completa_horas)

    return resultado


def a3_verificar_timezone(cmo: pd.DataFrame, carga: pd.DataFrame) -> dict:
    cmo_se = cmo[cmo["id_subsistema"] == "SE"].copy()
    cmo_se["hora"] = cmo_se["din_instante"].dt.hour
    perfil_cmo = cmo_se.groupby("hora")["val_cmo"].mean()

    carga_se = carga[carga["id_subsistema"] == "SE"].copy()
    carga_se["hora"] = carga_se["din_instante"].dt.hour
    perfil_carga = carga_se.groupby("hora")["val_num"].mean()

    hora_pico_cmo = int(perfil_cmo.idxmax())
    hora_pico_carga = int(perfil_carga.idxmax())
    hora_vale_cmo = int(perfil_cmo.idxmin())
    hora_vale_carga = int(perfil_carga.idxmin())

    correlacoes_por_lag = {}
    v_cmo = perfil_cmo.reindex(range(24)).values
    v_carga = perfil_carga.reindex(range(24)).values
    for lag in range(-12, 13):
        v_cmo_deslocado = np.roll(v_cmo, lag)
        corr = float(np.corrcoef(v_cmo_deslocado, v_carga)[0, 1])
        correlacoes_por_lag[lag] = corr

    melhor_lag = max(correlacoes_por_lag, key=correlacoes_por_lag.get)

    return {
        "perfil_cmo_por_hora": {int(h): float(v) for h, v in perfil_cmo.items()},
        "perfil_carga_por_hora": {int(h): float(v) for h, v in perfil_carga.items()},
        "hora_pico_cmo": hora_pico_cmo,
        "hora_pico_carga": hora_pico_carga,
        "hora_vale_cmo": hora_vale_cmo,
        "hora_vale_carga": hora_vale_carga,
        "correlacoes_por_lag": correlacoes_por_lag,
        "melhor_lag_horas": melhor_lag,
        "correlacao_no_melhor_lag": correlacoes_por_lag[melhor_lag],
        "correlacao_lag_0": correlacoes_por_lag[0],
    }


def main():
    print("Carregando CMO Semi-Horário 2024...")
    cmo = pd.read_parquet(CUSTO_DIR / "cmo_semi_horario_2024.parquet")
    cmo["id_subsistema"] = cmo["id_subsistema"].astype(str)

    print("Carregando carga 2024...")
    carga = carregar_carga_2024()

    print("\n=== A1/A2: integridade das semi-horas ===")
    integridade = a1_a2_integridade_semi_horas(cmo)
    for sub, info in integridade.items():
        print(f"{sub}: 2_semihoras={info['n_horas_com_2_semihoras']} 1_semihora={info['n_horas_com_1_semihora']} "
              f"mais_de_2={info['n_horas_com_mais_de_2']} total_com_dado={info['n_horas_total_com_dado']}")
        if info["n_horas_com_1_semihora"] > 0:
            for d in info["detalhe_horas_com_1"]:
                print(f"    1 semi-hora: hora={d['hora']} presente={d['din_instante_presente']} val_cmo={d['val_cmo']}")
    print(f"SE horas com 0 semi-horas (buraco completo na hora): {integridade['SE']['n_horas_com_0_semihoras']} de {integridade['SE']['n_horas_grade_completa_esperada']} esperadas")

    print("\n=== A3: verificação de timezone (medida, não suposição) ===")
    tz_check = a3_verificar_timezone(cmo, carga)
    print(f"Hora de pico CMO (SE): {tz_check['hora_pico_cmo']}h | Hora de pico carga (SE/CO): {tz_check['hora_pico_carga']}h")
    print(f"Hora de vale CMO (SE): {tz_check['hora_vale_cmo']}h | Hora de vale carga (SE/CO): {tz_check['hora_vale_carga']}h")
    print("Correlação perfil CMO x perfil carga, por lag (horas):")
    for lag, corr in sorted(tz_check["correlacoes_por_lag"].items()):
        marca = " <-- melhor" if lag == tz_check["melhor_lag_horas"] else ""
        print(f"  lag={lag:+d}h: r={corr:.4f}{marca}")
    print(f"Melhor lag: {tz_check['melhor_lag_horas']}h (r={tz_check['correlacao_no_melhor_lag']:.4f}); r no lag=0: {tz_check['correlacao_lag_0']:.4f}")

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    with open(INTERIM_DIR / "probe_cmo_integridade.json", "w", encoding="utf-8") as f:
        json.dump({"integridade": integridade, "timezone_check": tz_check}, f, indent=2, ensure_ascii=False, default=str)
    print("\nSalvo em data/interim/probe_cmo_integridade.json")


if __name__ == "__main__":
    main()
