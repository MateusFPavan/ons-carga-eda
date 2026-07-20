"""Primeiro modelo: sazonal-naive (semanal, régua principal) e naive diário
(referência secundária). Ver reports/ESCOPO.md seções 11 (Validação) e 12 (Métrica),
reports/FACTS.md seção H.

Não usa nenhuma feature além do próprio histórico do alvo — lê direto de
data/processed/carga_se.parquet, não de features_se.parquet. Fornece a estrutura de
origem deslizante (rodar_walkforward) para reuso pelos modelos seguintes (SARIMA,
Prophet, foundation models) — a previsão naive é só o primeiro `funcao_previsao`
plugado nela.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_features import valores_equivalentes, verificar_grade_regular  # noqa: E402

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
CUSTO_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "custo"
CARGA_SE_PATH = PROCESSED_DIR / "carga_se.parquet"

INICIO_AVALIACAO = pd.Timestamp("2024-01-01")
N_AMOSTRAS_VAZAMENTO = 30
SEED_VAZAMENTO = 42


class SanityCheckError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Estrutura de origem deslizante — reutilizável pelos próximos modelos
# ---------------------------------------------------------------------------

def gerar_origens(df: pd.DataFrame, inicio: pd.Timestamp) -> list:
    """Um dia D no período de avaliação = uma origem de previsão day-ahead (as 24
    horas de D são previstas de uma vez, a partir do corte em 00:00 de D)."""
    dias = sorted(df["din_instante"].dt.normalize().unique())
    return [pd.Timestamp(d) for d in dias if pd.Timestamp(d) >= inicio]


def rodar_walkforward(serie_alvo: pd.Series, origens: list, funcao_previsao) -> pd.DataFrame:
    """serie_alvo: pd.Series de val_cargaenergiahomwmed indexada por din_instante
    (asfreq('h'), ordenada). Para cada origem, corta a série ANTES de origem
    (`historico`) e chama `funcao_previsao(historico, origem)` — o histórico
    passado para a função nunca contém din_instante >= origem, então é
    estruturalmente impossível a previsão enxergar o dia D ou depois.
    `funcao_previsao` deve devolver uma pd.Series com as 24 horas de `origem`."""
    partes = []
    for origem in origens:
        idx_corte = serie_alvo.index.searchsorted(origem)
        historico = serie_alvo.iloc[:idx_corte]
        if len(historico) and historico.index[-1] >= origem:
            raise SanityCheckError(f"Corte malformado: histórico até {origem} contém {historico.index[-1]}.")
        previsao = funcao_previsao(historico, origem)
        horas_esperadas = pd.date_range(origem, periods=24, freq="h")
        if not previsao.index.equals(horas_esperadas):
            raise SanityCheckError(f"funcao_previsao não devolveu as 24 horas esperadas para origem {origem}.")
        partes.append(previsao)
    previsto = pd.concat(partes)
    return previsto.rename("previsto").rename_axis("din_instante").reset_index()


def previsor_naive(lag_horas: int):
    """Fábrica de previsor naive: previsão(H de D) = valor observado em (H de D) -
    lag_horas. lag_horas >= 24 garante, por construção geométrica, que a fonte
    (H de D - lag_horas) é sempre < 00:00 de D (a mais tardia é H=23 de D, cuja
    fonte fica em D-1 quando lag_horas>=24)."""
    if lag_horas < 24:
        raise SanityCheckError(f"Lag de {lag_horas}h < 24h não é válido para previsão day-ahead.")

    def prever(historico: pd.Series, origem: pd.Timestamp) -> pd.Series:
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        fontes = horas_alvo - pd.Timedelta(hours=lag_horas)
        valores = historico.reindex(fontes).to_numpy()
        return pd.Series(valores, index=horas_alvo)

    return prever


# ---------------------------------------------------------------------------
# Teste de vazamento — mesmo método do gerar_features: recorte independente
# (filtro booleano, não o searchsorted usado em rodar_walkforward) + mesma função
# de previsão, comparado contra a saída de produção.
# ---------------------------------------------------------------------------

def testar_vazamento(serie_alvo: pd.Series, previsto_producao: pd.DataFrame, previsor, nome_modelo: str,
                      n_amostras: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    origens_disponiveis = sorted(previsto_producao["din_instante"].dt.normalize().unique())
    origens_amostra = rng.choice(origens_disponiveis, size=min(n_amostras, len(origens_disponiveis)), replace=False)

    prod_indexado = previsto_producao.set_index("din_instante")["previsto"]
    divergencias = []
    n_comparacoes = 0

    for origem in origens_amostra:
        origem = pd.Timestamp(origem)
        truncado = serie_alvo[serie_alvo.index < origem]  # filtro independente do searchsorted
        recalc = previsor(truncado, origem)
        for ts, v_recalc in recalc.items():
            v_prod = prod_indexado.loc[ts]
            n_comparacoes += 1
            if not valores_equivalentes(v_prod, v_recalc):
                divergencias.append(f"{nome_modelo}@{ts} (recorte < {origem}): producao={v_prod!r} recalculo={v_recalc!r}")

    return {"n_origens_amostradas": len(origens_amostra), "n_comparacoes": n_comparacoes, "divergencias": divergencias}


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

def calcular_mae_insample_naive1(df: pd.DataFrame, inicio_avaliacao: pd.Timestamp) -> float:
    """Denominador do MASE (Hyndman): MAE do naive-1-passo (lag=1h) IN-SAMPLE, sobre
    o treino = tudo com din_instante < início da avaliação. NaN adjacentes a algum
    dos 28 NaN brutos são ignorados (skipna, padrão do pandas)."""
    treino = df.loc[df["din_instante"] < inicio_avaliacao].sort_values("din_instante")
    diffs_abs = treino["val_cargaenergiahomwmed"].diff().abs()
    mae = float(diffs_abs.mean())
    n_pares_validos = int(diffs_abs.notna().sum())
    return mae, n_pares_validos


def avaliar_modelo(df: pd.DataFrame, previsto: pd.DataFrame, mae_insample_naive1: float) -> dict:
    avaliacao = previsto.merge(
        df[["din_instante", "val_cargaenergiahomwmed", "is_dst_transition"]],
        on="din_instante", how="left", validate="one_to_one",
    )
    avaliacao["real"] = avaliacao["val_cargaenergiahomwmed"]

    motivo = pd.Series("incluida", index=avaliacao.index, dtype=object)
    motivo = motivo.mask(avaliacao["is_dst_transition"], "is_dst_transition")
    motivo = motivo.mask((motivo == "incluida") & avaliacao["real"].isna(), "nan_alvo")
    motivo = motivo.mask((motivo == "incluida") & avaliacao["previsto"].isna(), "nan_previsto")
    avaliacao["motivo_exclusao"] = motivo

    incluida = avaliacao[motivo == "incluida"].copy()
    incluida["erro"] = incluida["previsto"] - incluida["real"]

    mape = float((incluida["erro"].abs() / incluida["real"].abs()).mean() * 100)
    rmse = float(np.sqrt((incluida["erro"] ** 2).mean()))
    mae = float(incluida["erro"].abs().mean())
    mase = mae / mae_insample_naive1

    return {
        "n_total": len(avaliacao),
        "n_incluida": len(incluida),
        "contagem_exclusao": motivo.value_counts().to_dict(),
        "mape": mape,
        "rmse": rmse,
        "mae": mae,
        "mase": mase,
        "avaliacao": avaliacao,
    }


# ---------------------------------------------------------------------------
# Cobertura de CMO — checagem antes da métrica de custo
# ---------------------------------------------------------------------------

def checar_cobertura_cmo(ano_inicio: int, ano_fim: int) -> dict:
    anos_presentes = []
    anos_ausentes = []
    for ano in range(ano_inicio, ano_fim + 1):
        fpath = CUSTO_DIR / f"cmo_semi_horario_{ano}.parquet"
        if fpath.exists():
            anos_presentes.append(ano)
        else:
            anos_ausentes.append(ano)
    return {"anos_presentes": anos_presentes, "anos_ausentes": anos_ausentes, "completo": len(anos_ausentes) == 0}


# ---------------------------------------------------------------------------
def main():
    if not CARGA_SE_PATH.exists():
        raise SanityCheckError(f"Arquivo ausente: {CARGA_SE_PATH} (rode src/limpar.py primeiro).")

    df = pd.read_parquet(CARGA_SE_PATH)
    df = df.sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)

    if df["din_instante"].max() < INICIO_AVALIACAO:
        raise SanityCheckError("Série termina antes do início do período de avaliação.")

    fim_serie = df["din_instante"].max()
    print(f"Período de avaliação: {INICIO_AVALIACAO.date()} a {fim_serie.date()} (ver ESCOPO.md seção Validação).")

    origens = gerar_origens(df, INICIO_AVALIACAO)
    print(f"Origens de previsão day-ahead no período de avaliação: {len(origens)} dias.")

    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()

    mae_insample_naive1, n_pares_treino = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    print(f"\nDenominador do MASE (Hyndman): MAE do naive-1-passo (lag=1h) IN-SAMPLE no treino "
          f"(din_instante < {INICIO_AVALIACAO.date()}), {n_pares_treino} pares válidos = {mae_insample_naive1:.4f}")
    print("ATENÇÃO: este denominador é de 1 HORA à frente (persistência simples), não é o horizonte")
    print("day-ahead nem sazonal — é a definição padrão de Hyndman, não recalibrada para o horizonte")
    print("avaliado aqui. Séries horárias de carga têm forte autocorrelação hora-a-hora, então o")
    print("denominador tende a ser pequeno e o MASE dos naives day-ahead tende a ficar > 1 — não é bug.")

    modelos = {
        "naive_semanal (REGUA, lag_168h)": previsor_naive(168),
        "naive_diario (referência, lag_24h)": previsor_naive(24),
    }

    resultados = {}
    for nome, previsor in modelos.items():
        print(f"\n=== {nome} ===")
        previsto = rodar_walkforward(serie_alvo, origens, previsor)
        resultado = avaliar_modelo(df, previsto, mae_insample_naive1)
        resultados[nome] = resultado

        print(f"Horas-alvo totais no período: {resultado['n_total']}")
        for motivo, n in sorted(resultado["contagem_exclusao"].items()):
            print(f"  {motivo}: {n}")
        print(f"Horas incluídas na métrica estatística: {resultado['n_incluida']}")
        print(f"MAPE: {resultado['mape']:.4f}%")
        print(f"RMSE: {resultado['rmse']:.4f} MWh/h")
        print(f"MAE:  {resultado['mae']:.4f} MWh/h")
        print(f"MASE: {resultado['mase']:.4f} (denominador: naive-1-passo in-sample, ver acima)")

        print(f"Testando vazamento: {N_AMOSTRAS_VAZAMENTO} origens aleatórias (seed={SEED_VAZAMENTO})...")
        teste = testar_vazamento(serie_alvo, previsto, previsor, nome, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
        if teste["divergencias"]:
            print(f"  {len(teste['divergencias'])} DIVERGÊNCIA(S) DE VAZAMENTO:", file=sys.stderr)
            for d in teste["divergencias"][:10]:
                print(f"    - {d}", file=sys.stderr)
            raise SanityCheckError(f"Teste de vazamento falhou para {nome}: {len(teste['divergencias'])} divergência(s).")
        print(f"  OK — {teste['n_comparacoes']} comparações ({teste['n_origens_amostradas']} origens), 0 divergências.")

    # --- confirmar que os dois modelos dão números diferentes (senão há bug)
    nomes = list(resultados.keys())
    mae_a, mae_b = resultados[nomes[0]]["mae"], resultados[nomes[1]]["mae"]
    print(f"\n=== CONFIRMAÇÃO: modelos dão números diferentes ===")
    print(f"MAE {nomes[0]}: {mae_a:.6f}")
    print(f"MAE {nomes[1]}: {mae_b:.6f}")
    if valores_equivalentes(mae_a, mae_b, rtol=1e-9, atol=1e-9):
        raise SanityCheckError(
            f"MAE de {nomes[0]} e {nomes[1]} são idênticos ({mae_a} == {mae_b}) — "
            "isso indicaria um bug (os dois lags deveriam produzir previsões diferentes)."
        )
    print("OK — os dois modelos produzem previsões diferentes, como esperado (lags diferentes).")

    # --- métrica de custo: checar cobertura de CMO antes de tentar calcular
    print("\n=== MÉTRICA DE CUSTO ===")
    cobertura = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    print(f"Anos de CMO Semi-Horário necessários ({INICIO_AVALIACAO.year}-{fim_serie.year}): "
          f"presentes={cobertura['anos_presentes']}, ausentes={cobertura['anos_ausentes']}")
    if not cobertura["completo"]:
        print(
            f"\nPARADO ANTES DA MÉTRICA DE CUSTO: faltam os arquivos "
            f"{[f'cmo_semi_horario_{a}.parquet' for a in cobertura['anos_ausentes']]} em {CUSTO_DIR}."
        )
        print("O período de avaliação (2024-01-01 até o fim da série) exige CMO para todos os anos nesse")
        print("intervalo; só 2024 foi baixado (amostra da sondagem). Não vou baixar nada nem extrapolar/")
        print("inventar CMO para os anos ausentes — isso precisa ser decidido e baixado antes de calcular")
        print("custo total, custo médio por hora, ou a concentração de custo nas horas de CMO mais alto.")
    else:
        print("Cobertura de CMO completa para o período de avaliação — cálculo de custo não implementado")
        print("nesta rodada (não houve necessidade, cobertura já estava completa).")

    print("\nNenhum arquivo .md gerado. Nenhuma conclusão interpretativa — números e contagens acima.")


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
