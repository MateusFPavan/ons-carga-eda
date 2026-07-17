"""Parte A: efeito do DST no formato da curva de carga do SE/CO.

Recorte: dezembro+janeiro de cada "verão" — os únicos 2 meses de calendário
inteiramente dentro da vigência de DST nas 4 temporadas com DST (a temporada mais
tardia começa 2018-11-04, a mais precoce termina 2016-02-21 / mais tardia 2019-02-17;
dezembro e janeiro estão sempre 100% dentro do intervalo [início, fim] em todas as 4
temporadas). Os mesmos 2 meses de calendário são usados nas 4 temporadas sem DST.

COM DST: dez/2015+jan/2016, dez/2016+jan/2017, dez/2017+jan/2018, dez/2018+jan/2019
SEM DST: dez/2021+jan/2022, dez/2022+jan/2023, dez/2023+jan/2024, dez/2024+jan/2025
Excluídos por completo: 2019-20 e 2020-21 (transição do decreto + pandemia).

Não corrige, não decide — só agrega e reporta.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
FIG_DIR = Path(__file__).resolve().parent.parent / "reports" / "figures"
ANOS = list(range(2015, 2027))

# (ano_dezembro, ano_janeiro) por "verão"
VERWES_COM_DST = [(2015, 2016), (2016, 2017), (2017, 2018), (2018, 2019)]
VERWES_SEM_DST = [(2021, 2022), (2022, 2023), (2023, 2024), (2024, 2025)]

TIMESTAMPS_VIRADA_EXCLUIR = pd.to_datetime([
    "2015-10-18 00:00:00", "2016-10-16 00:00:00", "2017-10-15 00:00:00", "2018-11-04 00:00:00",
    "2015-02-21 23:00:00", "2016-02-20 23:00:00", "2017-02-18 23:00:00", "2018-02-17 23:00:00",
    "2019-02-16 23:00:00",
])


def load_seco() -> pd.DataFrame:
    frames = []
    for ano in ANOS:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        if not fpath.exists():
            continue
        df = pd.read_parquet(fpath, columns=["id_subsistema", "din_instante", "val_cargaenergiahomwmed"])
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        df = df[df["id_subsistema"] == "SE"].copy()
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    full["val_num"] = pd.to_numeric(full["val_cargaenergiahomwmed"], errors="coerce")
    full = full.dropna(subset=["val_num"])
    full = full[~full["din_instante"].isin(TIMESTAMPS_VIRADA_EXCLUIR)]
    return full


def selecionar_verao(df: pd.DataFrame, ano_dez: int, ano_jan: int) -> pd.DataFrame:
    mask_dez = (df["din_instante"].dt.year == ano_dez) & (df["din_instante"].dt.month == 12)
    mask_jan = (df["din_instante"].dt.year == ano_jan) & (df["din_instante"].dt.month == 1)
    return df[mask_dez | mask_jan].copy()


def montar_regime(df: pd.DataFrame, verwes: list, rotulo_regime: str) -> pd.DataFrame:
    partes = []
    for ano_dez, ano_jan in verwes:
        sub = selecionar_verao(df, ano_dez, ano_jan)
        sub["verao"] = f"{ano_dez}-{str(ano_jan)[2:]}"
        partes.append(sub)
    r = pd.concat(partes, ignore_index=True)
    r["regime"] = rotulo_regime
    r["dow"] = r["din_instante"].dt.dayofweek
    r["tipo_dia"] = r["dow"].apply(lambda d: "fim_de_semana" if d >= 5 else "dia_util")
    r["data"] = r["din_instante"].dt.date
    r["hora"] = r["din_instante"].dt.hour
    return r


def contagem_dias(df_regime: pd.DataFrame) -> dict:
    out = {}
    for tipo in ["dia_util", "fim_de_semana"]:
        sub = df_regime[df_regime["tipo_dia"] == tipo]
        n_dias = sub["data"].nunique()
        n_registros = len(sub)
        out[tipo] = {"n_dias": int(n_dias), "n_registros": int(n_registros), "registros_esperados": int(n_dias * 24)}
    return out


def perfil_horario(df_regime: pd.DataFrame, tipo_dia: str) -> pd.Series:
    sub = df_regime[df_regime["tipo_dia"] == tipo_dia]
    return sub.groupby("hora")["val_num"].mean()


def perfil_horario_normalizado(df_regime: pd.DataFrame, tipo_dia: str) -> pd.Series:
    sub = df_regime[df_regime["tipo_dia"] == tipo_dia].copy()
    media_diaria = sub.groupby("data")["val_num"].transform("mean")
    sub["val_normalizado"] = sub["val_num"] / media_diaria
    return sub.groupby("hora")["val_normalizado"].mean()


def pico_vale(perfil: pd.Series) -> dict:
    hora_pico = int(perfil.idxmax())
    valor_pico = float(perfil.max())
    hora_vale = int(perfil.idxmin())
    valor_vale = float(perfil.min())

    janela_tarde = perfil.loc[12:17]
    janela_noite = perfil.loc[18:23]
    hora_pico_tarde = int(janela_tarde.idxmax())
    valor_pico_tarde = float(janela_tarde.max())
    hora_pico_noite = int(janela_noite.idxmax())
    valor_pico_noite = float(janela_noite.max())

    return {
        "hora_pico_global": hora_pico, "valor_pico_global": valor_pico,
        "hora_vale": hora_vale, "valor_vale": valor_vale,
        "razao_pico_vale": valor_pico / valor_vale,
        "hora_pico_janela_tarde_12_17h": hora_pico_tarde, "valor_pico_janela_tarde": valor_pico_tarde,
        "hora_pico_janela_noite_18_23h": hora_pico_noite, "valor_pico_janela_noite": valor_pico_noite,
        "razao_pico_noite_sobre_pico_tarde": valor_pico_noite / valor_pico_tarde,
    }


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    full = load_seco()
    print(f"Linhas SE/CO carregadas (val parseável, viradas excluídas): {len(full)}")

    com_dst = montar_regime(full, VERWES_COM_DST, "com_dst")
    sem_dst = montar_regime(full, VERWES_SEM_DST, "sem_dst")

    resultado = {"contagem_dias": {}, "perfil_bruto": {}, "pico_vale_bruto": {}, "perfil_normalizado": {}, "pico_vale_normalizado": {}}

    for regime_nome, df_regime in [("com_dst", com_dst), ("sem_dst", sem_dst)]:
        resultado["contagem_dias"][regime_nome] = contagem_dias(df_regime)
        print(f"\n=== {regime_nome} — contagem de dias ===")
        print(json.dumps(resultado["contagem_dias"][regime_nome], indent=2, ensure_ascii=False))

        for tipo_dia in ["dia_util", "fim_de_semana"]:
            perfil = perfil_horario(df_regime, tipo_dia)
            resultado["perfil_bruto"].setdefault(regime_nome, {})[tipo_dia] = perfil.to_dict()
            pv = pico_vale(perfil)
            resultado["pico_vale_bruto"].setdefault(regime_nome, {})[tipo_dia] = pv
            print(f"[{regime_nome}/{tipo_dia}] bruto: pico_global={pv['hora_pico_global']}h ({pv['valor_pico_global']:.2f}) "
                  f"pico_tarde={pv['hora_pico_janela_tarde_12_17h']}h ({pv['valor_pico_janela_tarde']:.2f}) "
                  f"pico_noite={pv['hora_pico_janela_noite_18_23h']}h ({pv['valor_pico_janela_noite']:.2f}) "
                  f"vale={pv['hora_vale']}h ({pv['valor_vale']:.2f}) razao_pico_vale={pv['razao_pico_vale']:.4f} "
                  f"razao_noite_tarde={pv['razao_pico_noite_sobre_pico_tarde']:.4f}")

            perfil_norm = perfil_horario_normalizado(df_regime, tipo_dia)
            resultado["perfil_normalizado"].setdefault(regime_nome, {})[tipo_dia] = perfil_norm.to_dict()
            pv_norm = pico_vale(perfil_norm)
            resultado["pico_vale_normalizado"].setdefault(regime_nome, {})[tipo_dia] = pv_norm
            print(f"[{regime_nome}/{tipo_dia}] normalizado: pico_global={pv_norm['hora_pico_global']}h ({pv_norm['valor_pico_global']:.4f}) "
                  f"pico_tarde={pv_norm['hora_pico_janela_tarde_12_17h']}h ({pv_norm['valor_pico_janela_tarde']:.4f}) "
                  f"pico_noite={pv_norm['hora_pico_janela_noite_18_23h']}h ({pv_norm['valor_pico_janela_noite']:.4f}) "
                  f"vale={pv_norm['hora_vale']}h ({pv_norm['valor_vale']:.4f}) razao_pico_vale={pv_norm['razao_pico_vale']:.4f} "
                  f"razao_noite_tarde={pv_norm['razao_pico_noite_sobre_pico_tarde']:.4f}")

    with open(INTERIM_DIR / "dst_efeito.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)

    # gráficos: bruto e normalizado, dia útil e fim de semana, 4 curvas cada (2 regimes x bruto/norm já separado em 2 figuras)
    for tipo_dia, nome_arquivo_sufixo in [("dia_util", "dia_util"), ("fim_de_semana", "fim_de_semana")]:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        for ax, (usar_norm, titulo) in zip(axes, [(False, "bruto (MW médios)"), (True, "normalizado (fração da média diária)")]):
            for regime_nome, cor in [("com_dst", "tab:blue"), ("sem_dst", "tab:red")]:
                df_regime = com_dst if regime_nome == "com_dst" else sem_dst
                perfil = perfil_horario_normalizado(df_regime, tipo_dia) if usar_norm else perfil_horario(df_regime, tipo_dia)
                ax.plot(perfil.index, perfil.values, marker="o", markersize=3, color=cor, label=regime_nome)
            ax.set_title(f"SE/CO — {tipo_dia} — {titulo}")
            ax.set_xlabel("Hora do dia")
            ax.set_xticks(range(0, 24, 2))
            ax.legend()
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"f_dst_efeito_perfil_{nome_arquivo_sufixo}.png", dpi=120)
        plt.close(fig)
        print(f"Salvo: f_dst_efeito_perfil_{nome_arquivo_sufixo}.png")


if __name__ == "__main__":
    main()
