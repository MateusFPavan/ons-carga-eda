"""Teste independente de fuso do CMO Semi-Horário: agregação por semana operativa
comparada ao CMO Semanal, com e sem deslocamento de 3h. Mais o perfil intradiário
(teste estrutural). Não corrige, não decide o fuso — só mede e reporta.
"""
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CUSTO_DIR = RAW_DIR / "custo"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"


def carregar_semi_horario_se():
    df = pd.read_parquet(CUSTO_DIR / "cmo_semi_horario_2024.parquet")
    df["id_subsistema"] = df["id_subsistema"].astype(str)
    return df[df["id_subsistema"] == "SE"].copy()


def carregar_semanal_se():
    df = pd.read_parquet(CUSTO_DIR / "cmo_semanal_2024.parquet")
    df["id_subsistema"] = df["id_subsistema"].astype(str)
    return df[df["id_subsistema"] == "SE"].copy()


def agregar_por_semana(semi: pd.DataFrame, semanal: pd.DataFrame, deslocamento_horas: int) -> pd.DataFrame:
    """Para cada semana do CMO Semanal (din_instante = sexta-feira, fim da semana
    operativa, confirmado contra dat_fimsemana do CVU), agrega a média do
    Semi-Horário na janela [din_instante-6dias 00:00, din_instante 23:59:59],
    aplicando um deslocamento (em horas) aos timestamps do Semi-Horário antes de
    filtrar/agregar."""
    semi = semi.copy()
    semi["din_deslocado"] = semi["din_instante"] + pd.Timedelta(hours=deslocamento_horas)

    linhas = []
    for _, row in semanal.iterrows():
        fim_semana = row["din_instante"]
        inicio_semana = fim_semana - pd.Timedelta(days=6)
        janela = semi[(semi["din_deslocado"] >= inicio_semana) & (semi["din_deslocado"] <= fim_semana + pd.Timedelta(hours=23, minutes=59, seconds=59))]
        media_semi = float(janela["val_cmo"].mean()) if len(janela) else None
        linhas.append({
            "din_instante_semanal": str(fim_semana),
            "inicio_janela": str(inicio_semana),
            "fim_janela": str(fim_semana),
            "n_registros_semi_na_janela": int(len(janela)),
            "media_semi_horario": media_semi,
            "val_cmomediasemanal_declarado": float(row["val_cmomediasemanal"]),
            "diferenca": (media_semi - float(row["val_cmomediasemanal"])) if media_semi is not None else None,
        })
    return pd.DataFrame(linhas)


def perfil_intradiario(semi: pd.DataFrame) -> dict:
    s = semi.copy()
    s["hora"] = s["din_instante"].dt.hour
    perfil = s.groupby("hora")["val_cmo"].mean()
    amplitude = float(perfil.max() - perfil.min())
    media_geral = float(perfil.mean())
    coef_variacao = float(perfil.std() / media_geral) if media_geral else None
    return {
        "perfil_por_hora": {int(h): float(v) for h, v in perfil.items()},
        "hora_maximo": int(perfil.idxmax()),
        "valor_maximo": float(perfil.max()),
        "hora_minimo": int(perfil.idxmin()),
        "valor_minimo": float(perfil.min()),
        "amplitude_max_menos_min": amplitude,
        "media_geral_24h": media_geral,
        "coeficiente_variacao_entre_horas": coef_variacao,
    }


def main():
    print("Carregando CMO Semi-Horário e Semanal (SE, 2024)...")
    semi = carregar_semi_horario_se()
    semanal = carregar_semanal_se()
    print(f"Semi-horário: {len(semi)} linhas. Semanal: {len(semanal)} linhas.")

    # confirmação da convenção de semana: primeira/última data do semanal, dia da semana
    primeiras = sorted(semanal["din_instante"].unique())[:3]
    for d in primeiras:
        d = pd.Timestamp(d)
        print(f"  din_instante semanal: {d.date()} ({d.day_name()})")

    print("\n=== TAREFA 4: agregação semanal do Semi-Horário vs. CMO Semanal declarado ===")
    resultado_testes = {}
    for deslocamento in [0, 3, -3]:
        tabela = agregar_por_semana(semi, semanal, deslocamento)
        dif = tabela["diferenca"].dropna()
        resumo = {
            "n_semanas": int(len(tabela)),
            "n_semanas_com_dado": int(dif.notna().sum() if hasattr(dif, "notna") else len(dif)),
            "diferenca_media": float(dif.mean()),
            "diferenca_media_absoluta": float(dif.abs().mean()),
            "diferenca_max_absoluta": float(dif.abs().max()),
            "diferenca_min_absoluta": float(dif.abs().min()),
        }
        resultado_testes[f"deslocamento_{deslocamento}h"] = resumo
        print(f"\nDeslocamento {deslocamento:+d}h:")
        print(f"  N semanas: {resumo['n_semanas']}")
        print(f"  Diferença média (semi_horario_media - semanal_declarado): {resumo['diferenca_media']:.6f}")
        print(f"  Diferença média ABSOLUTA: {resumo['diferenca_media_absoluta']:.6f}")
        print(f"  Diferença máxima absoluta: {resumo['diferenca_max_absoluta']:.6f}")
        print(f"  Diferença mínima absoluta: {resumo['diferenca_min_absoluta']:.6f}")
        if deslocamento == 0:
            tabela_0 = tabela

    print("\nTabela completa (deslocamento 0h), primeiras 5 semanas:")
    print(tabela_0.head(5).to_string())

    print("\n=== TAREFA 5: perfil intradiário do CMO (SE, 2024) ===")
    perfil = perfil_intradiario(semi)
    print(f"Hora do máximo: {perfil['hora_maximo']}h ({perfil['valor_maximo']:.4f})")
    print(f"Hora do mínimo: {perfil['hora_minimo']}h ({perfil['valor_minimo']:.4f})")
    print(f"Amplitude (max-min): {perfil['amplitude_max_menos_min']:.4f}")
    print(f"Média geral das 24 horas: {perfil['media_geral_24h']:.4f}")
    print(f"Coeficiente de variação entre horas (desvio padrão / média): {perfil['coeficiente_variacao_entre_horas']:.4f}")
    for h in range(24):
        print(f"  {h:02d}h: {perfil['perfil_por_hora'][h]:.4f}")

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    saida = {
        "convencao_semana_amostras": [str(pd.Timestamp(d).date()) + " " + pd.Timestamp(d).day_name() for d in primeiras],
        "teste_agregacao_semanal": resultado_testes,
        "tabela_deslocamento_0h": tabela_0.to_dict(orient="records"),
        "perfil_intradiario": perfil,
    }
    with open(INTERIM_DIR / "probe_fuso_cmo.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, indent=2, ensure_ascii=False, default=str)
    print("\nSalvo em data/interim/probe_fuso_cmo.json")


if __name__ == "__main__":
    main()
