"""Parte B: sensibilidade da métrica de custo à agregação do CMO Semi-Horário
(30min -> 60min), usando um sazonal-naive (hora H do dia D-7) como instrumento
de medição de erro. Não é o modelo do projeto. Não otimiza, não escolhe variante.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CUSTO_DIR = RAW_DIR / "custo"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"

DST_TIMESTAMPS_2015_2019 = [
    "2015-02-21 23:00:00", "2015-10-18 00:00:00",
    "2016-02-20 23:00:00", "2016-10-16 00:00:00",
    "2017-02-18 23:00:00", "2017-10-15 00:00:00",
    "2018-02-17 23:00:00", "2018-11-04 00:00:00",
    "2019-02-16 23:00:00",
]

DIAS_SEM_CMO_2024 = ["2024-02-08", "2024-02-17", "2024-07-13", "2024-12-29"]


def carregar_carga_se(anos):
    frames = []
    for ano in anos:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        df = pd.read_parquet(fpath, columns=["id_subsistema", "din_instante", "val_cargaenergiahomwmed"])
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        df = df[df["id_subsistema"] == "SE"].copy()
        df["val_num"] = pd.to_numeric(df["val_cargaenergiahomwmed"], errors="coerce")
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    full = full.sort_values("din_instante").reset_index(drop=True)
    return full


def construir_naive(carga_se: pd.DataFrame) -> pd.DataFrame:
    """Previsão sazonal-naive: previsão(H,D) = observado(H, D-7)."""
    serie = carga_se.set_index("din_instante")["val_num"]
    df = pd.DataFrame({"din_instante": serie.index, "observado": serie.values})
    df = df.set_index("din_instante")
    previsao = serie.copy()
    previsao.index = previsao.index + pd.Timedelta(days=7)
    df["previsao_naive"] = previsao
    df = df.dropna(subset=["previsao_naive"])
    df["erro"] = df["observado"] - df["previsao_naive"]
    return df.reset_index()


def construir_variantes_cmo(cmo_se: pd.DataFrame) -> pd.DataFrame:
    cmo_se = cmo_se.copy()
    cmo_se["hora_local"] = cmo_se["din_instante"].dt.floor("h")
    cmo_se["ordem_semihora"] = cmo_se.groupby("hora_local").cumcount()

    media = cmo_se.groupby("hora_local")["val_cmo"].mean().rename("cmo_media")
    maximo = cmo_se.groupby("hora_local")["val_cmo"].max().rename("cmo_maximo")
    primeira = cmo_se[cmo_se["ordem_semihora"] == 0].set_index("hora_local")["val_cmo"].rename("cmo_primeira")

    n_semihoras = cmo_se.groupby("hora_local").size().rename("n_semihoras")

    tabela = pd.concat([media, maximo, primeira, n_semihoras], axis=1).reset_index()
    return tabela


def main():
    print("Carregando carga SE (2023-2024, para permitir naive nos primeiros 7 dias de 2024)...")
    carga_se = carregar_carga_se([2023, 2024])
    naive = construir_naive(carga_se)
    naive_2024 = naive[naive["din_instante"].dt.year == 2024].copy()
    print(f"Linhas de naive em 2024: {len(naive_2024)}")

    dst_em_2024 = [t for t in DST_TIMESTAMPS_2015_2019 if pd.Timestamp(t).year == 2024]
    print(f"Timestamps de is_dst_transition (2015-2019) que caem em 2024: {len(dst_em_2024)} (confirmação: nenhum, já que a lista é só 2015-2019)")

    print("\nCarregando CMO Semi-Horário 2024 (SE)...")
    cmo = pd.read_parquet(CUSTO_DIR / "cmo_semi_horario_2024.parquet")
    cmo["id_subsistema"] = cmo["id_subsistema"].astype(str)
    cmo_se = cmo[cmo["id_subsistema"] == "SE"].copy()

    variantes = construir_variantes_cmo(cmo_se)
    print(f"Horas com CMO (SE), 2024: {len(variantes)}")
    print("Distribuição de n_semihoras por hora:")
    print(variantes["n_semihoras"].value_counts().to_string())

    # B1: como cada variante trata horas com 1 semi-hora (já sabemos, pela Parte A, que são 0 — confirmar aqui)
    horas_1_semihora = variantes[variantes["n_semihoras"] == 1]
    print(f"\nHoras com exatamente 1 semi-hora (deveriam ser tratadas por igual nas 3 variantes, já que média/máximo/primeira colapsam ao único valor): {len(horas_1_semihora)}")

    # merge naive com variantes de CMO
    merged = pd.merge(naive_2024, variantes, left_on="din_instante", right_on="hora_local", how="left")
    n_com_cmo = merged["cmo_media"].notna().sum()
    n_sem_cmo = merged["cmo_media"].isna().sum()
    print(f"\nHoras de naive em 2024 com CMO correspondente: {n_com_cmo}")
    print(f"Horas de naive em 2024 SEM CMO correspondente: {n_sem_cmo}")

    dias_sem_cmo_set = set(pd.Timestamp(d).date() for d in DIAS_SEM_CMO_2024)
    merged["dia"] = merged["din_instante"].dt.date
    merged["tem_cmo_dia"] = ~merged["dia"].isin(dias_sem_cmo_set)

    # métrica estatística (MAPE/RMSE): TODAS as horas do naive em 2024
    erro_todas = merged["erro"]
    obs_todas = merged["observado"]
    mape_2024 = float((erro_todas.abs() / obs_todas.abs()).mean() * 100)
    rmse_2024 = float(np.sqrt((erro_todas ** 2).mean()))
    mae_2024 = float(erro_todas.abs().mean())
    print(f"\n=== B4: métrica estatística do naive, 2024 inteiro (SE/CO) ===")
    print(f"N horas (métrica estatística): {len(merged)}")
    print(f"MAPE: {mape_2024:.4f}%  RMSE: {rmse_2024:.4f} MW  MAE: {mae_2024:.4f} MW")

    # métrica de custo: só horas com CMO E fora dos 4 dias sem CMO
    custo_base = merged[merged["tem_cmo_dia"] & merged["cmo_media"].notna()].copy()
    print(f"\nN horas (métrica de custo, excluindo 4 dias sem CMO): {len(custo_base)}")

    resultado = {
        "n_horas_naive_2024": int(len(merged)),
        "n_horas_com_cmo": int(n_com_cmo),
        "n_horas_sem_cmo": int(n_sem_cmo),
        "n_dst_em_2024": len(dst_em_2024),
        "mape_2024_pct": mape_2024,
        "rmse_2024_mw": rmse_2024,
        "mae_2024_mw": mae_2024,
        "n_horas_metrica_custo": int(len(custo_base)),
        "n_horas_metrica_estatistica": int(len(merged)),
        "distribuicao_n_semihoras": {str(k): int(v) for k, v in variantes["n_semihoras"].value_counts().to_dict().items()},
    }

    print("\n=== B2/B3: custo por variante ===")
    custos_por_variante = {}
    for nome_var, col in [("media", "cmo_media"), ("maximo", "cmo_maximo"), ("primeira_semihora", "cmo_primeira")]:
        custo_base[f"custo_{nome_var}"] = custo_base["erro"].abs() * custo_base[col] * 1.0
        total = float(custo_base[f"custo_{nome_var}"].sum())
        media_h = float(custo_base[f"custo_{nome_var}"].mean())
        mediana_h = float(custo_base[f"custo_{nome_var}"].median())
        custos_por_variante[nome_var] = {"total": total, "media_por_hora": media_h, "mediana_por_hora": mediana_h}
        print(f"{nome_var}: total={total:,.2f} media_hora={media_h:.4f} mediana_hora={mediana_h:.4f}")

    total_a = custos_por_variante["media"]["total"]
    total_b = custos_por_variante["maximo"]["total"]
    total_c = custos_por_variante["primeira_semihora"]["total"]
    pct_b_de_a = total_b / total_a * 100
    pct_c_de_a = total_c / total_a * 100
    print(f"\nCusto total (b) máximo como % de (a) média: {pct_b_de_a:.4f}%")
    print(f"Custo total (c) primeira semi-hora como % de (a) média: {pct_c_de_a:.4f}%")

    corr_ab = float(custo_base["custo_media"].corr(custo_base["custo_maximo"]))
    corr_ac = float(custo_base["custo_media"].corr(custo_base["custo_primeira_semihora"]))
    corr_bc = float(custo_base["custo_maximo"].corr(custo_base["custo_primeira_semihora"]))
    print(f"Correlação custo(a,b)={corr_ab:.6f} custo(a,c)={corr_ac:.6f} custo(b,c)={corr_bc:.6f}")

    def pct_mudanca(base, outro):
        with np.errstate(divide="ignore", invalid="ignore"):
            mudanca = np.where(base != 0, np.abs(outro - base) / np.abs(base), np.where(outro != 0, np.inf, 0))
        return mudanca

    mud_ab = pct_mudanca(custo_base["custo_media"].values, custo_base["custo_maximo"].values)
    mud_ac = pct_mudanca(custo_base["custo_media"].values, custo_base["custo_primeira_semihora"].values)
    n_ab_10pct = int((mud_ab > 0.10).sum())
    n_ac_10pct = int((mud_ac > 0.10).sum())
    idx_ab = set(custo_base.index[mud_ab > 0.10])
    idx_ac = set(custo_base.index[mud_ac > 0.10])
    mesmo_conjunto = idx_ab == idx_ac
    print(f"N horas onde (b) muda o custo em >10% vs (a): {n_ab_10pct} de {len(custo_base)}")
    print(f"N horas onde (c) muda o custo em >10% vs (a): {n_ac_10pct} de {len(custo_base)}")
    print(f"É o mesmo conjunto de horas em ambos os casos? {mesmo_conjunto}")

    resultado["custos_por_variante"] = custos_por_variante
    resultado["pct_b_de_a"] = pct_b_de_a
    resultado["pct_c_de_a"] = pct_c_de_a
    resultado["correlacao_ab"] = corr_ab
    resultado["correlacao_ac"] = corr_ac
    resultado["correlacao_bc"] = corr_bc
    resultado["n_horas_b_muda_mais_10pct"] = n_ab_10pct
    resultado["n_horas_c_muda_mais_10pct"] = n_ac_10pct
    resultado["mesmo_conjunto_horas_b_e_c"] = mesmo_conjunto

    print("\n=== B5: efeito de CMO zero e negativo ===")
    n_zero = int((custo_base["cmo_media"] == 0).sum())
    erro_medio_zero = float(custo_base.loc[custo_base["cmo_media"] == 0, "erro"].abs().mean()) if n_zero else None
    n_neg = int((custo_base["cmo_media"] < 0).sum())
    erro_medio_neg = float(custo_base.loc[custo_base["cmo_media"] < 0, "erro"].abs().mean()) if n_neg else None
    print(f"Horas com CMO médio == 0: {n_zero}, erro médio absoluto do naive nessas horas: {erro_medio_zero}")
    print(f"Horas com CMO médio < 0: {n_neg}, erro médio absoluto do naive nessas horas: {erro_medio_neg}")

    p90 = custo_base["cmo_media"].quantile(0.90)
    top10 = custo_base[custo_base["cmo_media"] >= p90]
    pct_custo_top10 = float(top10["custo_media"].sum() / total_a * 100)
    print(f"Limiar do decil 90 do CMO médio: {p90:.4f}")
    print(f"N horas no top 10% de CMO: {len(top10)}")
    print(f"% do custo total (variante média) vindo dessas horas: {pct_custo_top10:.4f}%")

    resultado["n_horas_cmo_zero"] = n_zero
    resultado["erro_medio_abs_cmo_zero"] = erro_medio_zero
    resultado["n_horas_cmo_negativo"] = n_neg
    resultado["erro_medio_abs_cmo_negativo"] = erro_medio_neg
    resultado["limiar_p90_cmo"] = float(p90)
    resultado["n_horas_top10pct_cmo"] = int(len(top10))
    resultado["pct_custo_top10pct_cmo"] = pct_custo_top10

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    with open(INTERIM_DIR / "probe_sensibilidade_custo.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    print("\nSalvo em data/interim/probe_sensibilidade_custo.json")


if __name__ == "__main__":
    main()
