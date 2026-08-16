"""Teste de contaminação: janela pós-cutoff de pré-treino (ESCOPO.md seção 16 —
ataca a limitação sem re-treinar nada). Chronos-2 (`amazon/chronos-2`) não publica
uma data de corte exata do corpus de pré-treino (verificado: arXiv:2510.15821,
model card no Hugging Face, discussão #450 do repositório
amazon-science/chronos-forecasting — nenhum menciona uma data de corte explícita).

PROXY CONSERVADORA, declarada, não inventada: a data de RELEASE do checkpoint
(`amazon/chronos-2` publicado no Hugging Face em 2025-10-20, dias após o artigo
técnico em 2025-10-17 — verificado por busca, não por memória). É conservadora
porque o corte real do corpus tem que ser IGUAL OU ANTERIOR à data de publicação
do artigo (o modelo já estava treinado quando o artigo foi escrito) — logo
qualquer origem estritamente posterior ao release está garantidamente também
posterior ao corte real, não importa qual seja.

Recomputa das previsões JÁ SALVAS (reusa coletar_avaliacoes() de
custo_assimetrico.py) — filtra por ORIGEM (dia sendo previsto), não re-treina
nada. IMPORTANTE, declarado com precisão: isto só descarta que o modelo viu
ESTAS HORAS ESPECÍFICAS (2015-2026, SE/CO) no pré-treino — não descarta
contaminação por padrões GENÉRICOS de dados de energia/eletricidade no corpus
(Electricity, London Smart Meters, Buildings 900K, Solar, Wind Farms — já
documentado em ESCOPO.md seção 16), que é uma forma de contaminação diferente e
este teste não a ataca.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from custo_assimetrico import coletar_avaliacoes  # noqa: E402
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, INICIO_AVALIACAO, SanityCheckError, calcular_custo,
    calcular_mae_insample_naive1, calcular_mae_insample_naive_sazonal, carregar_cmo_horario_se,
    checar_cobertura_cmo,
)

RAIZ = Path(__file__).resolve().parent.parent

# Fonte: arXiv:2510.15821 (artigo, 2025-10-17) + amazon/chronos-2 no Hugging Face
# (release do checkpoint, 2025-10-20) — busca verificada, não memória, não inventada.
CUTOFF_PRETREINO_PROXY = pd.Timestamp("2025-10-20")


def _metricas_janela(avaliacao: pd.DataFrame, cmo_horario: pd.Series, mae1: float, mae_saz: float,
                      origem_min=None) -> dict:
    aval = avaliacao.copy()
    aval["origem"] = aval["din_instante"].dt.normalize()
    if origem_min is not None:
        aval = aval[aval["origem"] > origem_min]

    incluida = aval[aval["motivo_exclusao"] == "incluida"].copy()
    if len(incluida) == 0:
        return {"n_origens": 0, "n_horas": 0, "mape": None, "mase_1passo": None, "mase_sazonal": None, "custo_total": None}
    mae = float(incluida["erro"].abs().mean())
    mape = float((incluida["erro"].abs() / incluida["real"].abs()).mean() * 100)
    custo = calcular_custo(aval, cmo_horario)

    return {
        "n_origens": int(aval["origem"].nunique()),
        "n_horas": len(incluida),
        "mape": mape,
        "mase_1passo": mae / mae1,
        "mase_sazonal": mae / mae_saz,
        "custo_total": custo["custo_total"],
    }


def calcular_todos() -> dict:
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    fim_serie = df["din_instante"].max()
    mae1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)
    cobertura_cmo = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    if not cobertura_cmo["completo"]:
        raise SanityCheckError(f"CMO incompleto ({cobertura_cmo}) — não dá para calcular custo na janela pós-cutoff.")
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"])

    avaliacoes, _ = coletar_avaliacoes()

    if CUTOFF_PRETREINO_PROXY >= fim_serie:
        raise SanityCheckError(
            f"Cutoff proxy ({CUTOFF_PRETREINO_PROXY.date()}) é posterior ao fim da série "
            f"({fim_serie.date()}) — não há janela pós-cutoff para testar."
        )

    linhas = []
    for nome, avaliacao in avaliacoes.items():
        completo = _metricas_janela(avaliacao, cmo_horario, mae1, mae_saz, origem_min=None)
        pos_cutoff = _metricas_janela(avaliacao, cmo_horario, mae1, mae_saz, origem_min=CUTOFF_PRETREINO_PROXY)
        linhas.append({"modelo": nome, "janela": "período completo (2024-01-01+)", **completo})
        linhas.append({"modelo": nome, "janela": f"pós-cutoff ({CUTOFF_PRETREINO_PROXY.date()}+)", **pos_cutoff})

    tabela = pd.DataFrame(linhas)
    return {"tabela": tabela, "cutoff": CUTOFF_PRETREINO_PROXY, "fim_serie": fim_serie}


def main():
    resultado = calcular_todos()
    tabela = resultado["tabela"]

    print(f"Cutoff de pré-treino (proxy conservadora, checkpoint release): {resultado['cutoff'].date()}")
    print(f"Fonte: arXiv:2510.15821 (artigo, 2025-10-17) + amazon/chronos-2 no Hugging Face (release, 2025-10-20).")
    print(f"Fim da série avaliada: {resultado['fim_serie'].date()}")

    print("\n=== MASE/MAPE/custo — período completo vs. janela pós-cutoff ===")
    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(tabela.round(4).to_string(index=False))

    print("\n=== Chronos-2 continua vencendo na janela pós-cutoff? ===")
    pos = tabela[tabela["janela"].str.startswith("pós-cutoff")].dropna(subset=["mase_sazonal"])
    if len(pos) >= 2:
        vencedor_pos = pos.loc[pos["mase_sazonal"].idxmin(), "modelo"]
        print(f"Vencedor por MASE(sazonal) na janela pós-cutoff: {vencedor_pos}")
        completo = tabela[tabela["janela"].str.startswith("período completo")].dropna(subset=["mase_sazonal"])
        vencedor_completo = completo.loc[completo["mase_sazonal"].idxmin(), "modelo"]
        print(f"Vencedor por MASE(sazonal) no período completo: {vencedor_completo}")
        print(f"Mesmo vencedor: {'SIM' if vencedor_pos == vencedor_completo else 'NÃO'}")

        chronos_completo = completo[completo["modelo"] == "Chronos-2"]
        chronos_pos = pos[pos["modelo"] == "Chronos-2"]
        if len(chronos_completo) and len(chronos_pos):
            mase_c = float(chronos_completo["mase_sazonal"].iloc[0])
            mase_p = float(chronos_pos["mase_sazonal"].iloc[0])
            print(f"\nChronos-2 MASE(sazonal): completo={mase_c:.4f} pós-cutoff={mase_p:.4f} "
                  f"(diferença: {(mase_p - mase_c):+.4f}, {'piorou' if mase_p > mase_c else 'melhorou ou igual'})")

    print("\n=== O QUE ESTE TESTE PROVA E O QUE NÃO PROVA ===")
    print("PROVA (se o resultado se mantiver): a vantagem do Chronos-2 não depende de ter memorizado")
    print("ESTAS horas específicas (carga SE/CO, 2015-2026) durante o pré-treino — essas horas são")
    print("posteriores ao release do checkpoint, logo posteriores ao corte real do corpus de pré-treino.")
    print("NÃO PROVA: que o corpus de pré-treino não contém dados de energia/eletricidade GENÉRICOS")
    print("(outros medidores, outras redes, outros países) que possam ter ensinado ao modelo padrões")
    print("estruturais de carga elétrica aplicáveis aqui por analogia — essa forma de contaminação")
    print("(já documentada em ESCOPO.md seção 16, arXiv:2510.15821 Tabela 6: Electricity, London Smart")
    print("Meters, Buildings 900K, Solar, Wind Farms) não é testável a partir daqui.")


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
