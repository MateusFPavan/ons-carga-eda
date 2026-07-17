"""Gráficos exploratórios brutos (sem conclusão), focados no subsistema SE/CO
(id_subsistema == 'SE'). Salva 5 PNGs em reports/figures/.

Nenhuma limpeza, remoção de outlier ou imputação é feita aqui — os valores
não-parseáveis (strings vazias) são apenas excluídos do cálculo de médias,
como na sondagem descritiva (src/probe_descriptive.py).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
FIG_DIR = Path(__file__).resolve().parent.parent / "reports" / "figures"
ANOS = list(range(2015, 2027))

DIAS_SEMANA_PT = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}


def load_seco() -> pd.DataFrame:
    frames = []
    for ano in ANOS:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        if not fpath.exists():
            continue
        df = pd.read_parquet(
            fpath, columns=["id_subsistema", "din_instante", "val_cargaenergiahomwmed"]
        )
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        df = df[df["id_subsistema"] == "SE"].copy()
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    full["val_num"] = pd.to_numeric(full["val_cargaenergiahomwmed"], errors="coerce")
    full = full.dropna(subset=["val_num"])
    full = full.sort_values("din_instante").reset_index(drop=True)
    return full


def plot_a_serie_completa(df: pd.DataFrame):
    daily = df.set_index("din_instante")["val_num"].resample("D").mean()
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(daily.index, daily.values, linewidth=0.6)
    ax.set_title("SE/CO — Carga média diária, 2015–2026 (bruto, sem tratamento)")
    ax.set_xlabel("Data")
    ax.set_ylabel("Carga média diária (MW médios)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "a_serie_completa_2015_2026_seco.png", dpi=120)
    plt.close(fig)


def plot_b_perfil_dia_semana(df: pd.DataFrame):
    d = df.copy()
    d["hora"] = d["din_instante"].dt.hour
    d["dow"] = d["din_instante"].dt.dayofweek
    d["categoria"] = d["dow"].apply(
        lambda x: "Sábado" if x == 5 else ("Domingo" if x == 6 else "Dia útil (seg–sex)")
    )
    perfil = d.groupby(["categoria", "hora"])["val_num"].mean().unstack(level=0)

    fig, ax = plt.subplots(figsize=(10, 6))
    for cat in ["Dia útil (seg–sex)", "Sábado", "Domingo"]:
        ax.plot(perfil.index, perfil[cat], marker="o", markersize=3, label=cat)
    ax.set_title("SE/CO — Perfil horário médio: dia útil vs. sábado vs. domingo (2015–2026, bruto)")
    ax.set_xlabel("Hora do dia")
    ax.set_ylabel("Carga média (MW médios)")
    ax.set_xticks(range(0, 24))
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "b_perfil_horario_dia_semana_seco.png", dpi=120)
    plt.close(fig)


def plot_c_perfil_por_mes(df: pd.DataFrame):
    d = df.copy()
    d["hora"] = d["din_instante"].dt.hour
    d["mes"] = d["din_instante"].dt.month
    perfil = d.groupby(["mes", "hora"])["val_num"].mean().unstack(level=0)

    fig, ax = plt.subplots(figsize=(11, 7))
    cmap = plt.get_cmap("twilight_shifted", 12)
    for mes in range(1, 13):
        ax.plot(perfil.index, perfil[mes], color=cmap(mes - 1), label=MESES_PT[mes])
    ax.set_title("SE/CO — Perfil horário médio por mês (2015–2026, bruto)")
    ax.set_xlabel("Hora do dia")
    ax.set_ylabel("Carga média (MW médios)")
    ax.set_xticks(range(0, 24))
    ax.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "c_perfil_horario_por_mes_seco.png", dpi=120)
    plt.close(fig)


def plot_d_pandemia_2020(df: pd.DataFrame):
    mask = (df["din_instante"] >= "2020-03-01") & (df["din_instante"] < "2021-01-01")
    d = df.loc[mask].set_index("din_instante")["val_num"].resample("D").mean()

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(d.index, d.values, linewidth=1.0, color="firebrick")
    ax.set_title("SE/CO — Carga média diária, março–dezembro de 2020 (bruto, sem tratamento)")
    ax.set_xlabel("Data")
    ax.set_ylabel("Carga média diária (MW médios)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "d_recorte_pandemia_2020_seco.png", dpi=120)
    plt.close(fig)


def plot_e_semana_tipica(df: pd.DataFrame):
    # Semanas fixas (sem aleatoriedade): primeira semana completa (seg-dom) de maio,
    # em 2019 e em 2023 — mês sem feriados nacionais nem Carnaval/Corpus Christi.
    janela_2019 = ("2019-05-06", "2019-05-13")
    janela_2023 = ("2023-05-08", "2023-05-15")

    def semana(inicio, fim):
        mask = (df["din_instante"] >= inicio) & (df["din_instante"] < fim)
        s = df.loc[mask].set_index("din_instante")["val_num"]
        s.index = pd.RangeIndex(len(s))  # horas corridas 0..167 para sobrepor
        return s

    s2019 = semana(*janela_2019)
    s2023 = semana(*janela_2023)

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(s2019.index, s2019.values, label=f"Semana de {janela_2019[0]} a {janela_2019[1]} (2019)")
    ax.plot(s2023.index, s2023.values, label=f"Semana de {janela_2023[0]} a {janela_2023[1]} (2023)")
    ax.set_title("SE/CO — Semana típica sobreposta: 2019 vs. 2023 (bruto, horário)")
    ax.set_xlabel("Hora corrida na semana (0 = segunda 00h)")
    ax.set_ylabel("Carga (MW médios)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "e_semana_tipica_2019_vs_2023_seco.png", dpi=120)
    plt.close(fig)
    return janela_2019, janela_2023, len(s2019), len(s2023)


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = load_seco()
    print(f"Linhas SE/CO carregadas (val parseável): {len(df)}")

    plot_a_serie_completa(df)
    print("Salvo: a_serie_completa_2015_2026_seco.png")

    plot_b_perfil_dia_semana(df)
    print("Salvo: b_perfil_horario_dia_semana_seco.png")

    plot_c_perfil_por_mes(df)
    print("Salvo: c_perfil_horario_por_mes_seco.png")

    plot_d_pandemia_2020(df)
    print("Salvo: d_recorte_pandemia_2020_seco.png")

    janela_2019, janela_2023, n2019, n2023 = plot_e_semana_tipica(df)
    print(f"Salvo: e_semana_tipica_2019_vs_2023_seco.png (n_2019={n2019}h janela={janela_2019}, n_2023={n2023}h janela={janela_2023})")


if __name__ == "__main__":
    main()
