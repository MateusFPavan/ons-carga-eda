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


def avaliar_modelo(df: pd.DataFrame, previsto: pd.DataFrame, mae_insample_naive1: float,
                    mae_insample_naive_sazonal: float) -> dict:
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
    avaliacao.loc[incluida.index, "erro"] = incluida["erro"]

    mape = float((incluida["erro"].abs() / incluida["real"].abs()).mean() * 100)
    rmse = float(np.sqrt((incluida["erro"] ** 2).mean()))
    mae = float(incluida["erro"].abs().mean())
    mase_naive1 = mae / mae_insample_naive1
    mase_sazonal = mae / mae_insample_naive_sazonal

    return {
        "n_total": len(avaliacao),
        "n_incluida": len(incluida),
        "contagem_exclusao": motivo.value_counts().to_dict(),
        "mape": mape,
        "rmse": rmse,
        "mae": mae,
        "mase_naive1": mase_naive1,
        "mase_sazonal": mase_sazonal,
        "avaliacao": avaliacao,
    }


def calcular_mae_insample_naive_sazonal(df: pd.DataFrame, inicio_avaliacao: pd.Timestamp, lag_horas: int = 168) -> tuple:
    """Denominador alternativo do MASE: MAE do naive SAZONAL SEMANAL (lag=168h)
    IN-SAMPLE sobre o treino. Convenção da literatura de carga e base de
    comparação com Simeone (2026), cujo MASE ~0,31 usa naive sazonal como
    referência."""
    treino = df.loc[df["din_instante"] < inicio_avaliacao].sort_values("din_instante")
    serie = treino.set_index("din_instante")["val_cargaenergiahomwmed"].asfreq("h")
    diffs_abs = (serie - serie.shift(lag_horas)).abs()
    mae = float(diffs_abs.mean())
    n_pares_validos = int(diffs_abs.notna().sum())
    return mae, n_pares_validos


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


def carregar_cmo_horario_se(anos: list) -> pd.Series:
    """CMO do SE, agregado de 30min para grade horária pela MÉDIA das duas
    semi-horas — decisão travada em FACTS.md seção H/K1. Retorna série indexada
    por din_instante horário (hora local, mesma convenção da carga — fato
    derivado, FACTS.md seção K3, reconfirmado para 2025-2026 nesta rodada)."""
    frames = []
    for ano in anos:
        fpath = CUSTO_DIR / f"cmo_semi_horario_{ano}.parquet"
        dfc = pd.read_parquet(fpath, columns=["id_subsistema", "din_instante", "val_cmo"])
        dfc["id_subsistema"] = dfc["id_subsistema"].astype(str)
        # val_cmo diverge de dtype entre anos (float64 em 2024-2025, str em 2026 —
        # mesmo padrão de divergência já documentado para a carga em FACTS.md seção
        # B). Cast explícito, sempre — não confiar no dtype de origem.
        dfc["val_cmo"] = pd.to_numeric(dfc["val_cmo"], errors="coerce")
        frames.append(dfc[dfc["id_subsistema"] == "SE"])
    cmo_se = pd.concat(frames, ignore_index=True)
    n_nao_conversiveis = int(cmo_se["val_cmo"].isna().sum())
    if n_nao_conversiveis:
        print(f"  AVISO: {n_nao_conversiveis} valores de val_cmo não puderam ser convertidos para número (viraram NaN).")
    cmo_se["hora_local"] = cmo_se["din_instante"].dt.floor("h")
    media_horaria = cmo_se.groupby("hora_local")["val_cmo"].mean()
    return media_horaria.rename("cmo_horario")


def calcular_custo(avaliacao: pd.DataFrame, cmo_horario: pd.Series) -> dict:
    """custo = |erro_MW| x CMO_horário x 1h (ESCOPO.md seção 12a). Aplicado só às
    horas já incluídas na métrica estatística (motivo_exclusao == 'incluida') e
    que além disso têm CMO disponível — horas sem CMO ficam fora do custo, mas
    permanecem na estatística."""
    incluida_stat = avaliacao[avaliacao["motivo_exclusao"] == "incluida"].copy()
    incluida_stat["cmo"] = incluida_stat["din_instante"].map(cmo_horario)
    tem_cmo = incluida_stat["cmo"].notna()

    custo_base = incluida_stat[tem_cmo].copy()
    custo_base["erro_abs"] = custo_base["erro"].abs()
    custo_base["custo"] = custo_base["erro_abs"] * custo_base["cmo"]

    custo_total = float(custo_base["custo"].sum())
    custo_medio_hora = float(custo_base["custo"].mean())
    limiar_p90 = float(custo_base["cmo"].quantile(0.90))
    top10 = custo_base[custo_base["cmo"] >= limiar_p90]
    pct_custo_top10 = float(top10["custo"].sum() / custo_total * 100) if custo_total else float("nan")

    return {
        "n_incluida_estatistica": len(incluida_stat),
        "n_sem_cmo": int((~tem_cmo).sum()),
        "n_incluida_custo": len(custo_base),
        "custo_total": custo_total,
        "custo_medio_hora": custo_medio_hora,
        "limiar_p90_cmo": limiar_p90,
        "n_horas_top10pct_cmo": int(len(top10)),
        "pct_custo_top10pct_cmo": pct_custo_top10,
    }


def calcular_custo_assimetrico(avaliacao: pd.DataFrame, cmo_horario: pd.Series, fator_sub: float) -> dict:
    """Extensão de calcular_custo (ESCOPO.md seção 12f): subprevisão (previsto <
    real, erro < 0 — falta energia, reserva rápida/corte no extremo) custa
    fator_sub vezes mais que superprevisão (previsto > real, erro > 0 — sobra
    capacidade), ambas ao preço marginal (CMO). fator_sub=1.0 reduz
    algebricamente ao custo simétrico de calcular_custo — |erro| não distingue
    sinal, então custo_total(fator_sub=1.0) == calcular_custo(...)['custo_total']
    por construção, não por coincidência numérica. Mesmo escopo de linhas
    (motivo_exclusao == 'incluida' e CMO disponível) que calcular_custo, para os
    dois números serem diretamente comparáveis."""
    incluida_stat = avaliacao[avaliacao["motivo_exclusao"] == "incluida"].copy()
    incluida_stat["cmo"] = incluida_stat["din_instante"].map(cmo_horario)
    tem_cmo = incluida_stat["cmo"].notna()

    custo_base = incluida_stat[tem_cmo].copy()
    custo_base["erro_abs"] = custo_base["erro"].abs()
    eh_subprevisao = custo_base["erro"] < 0  # previsto < real
    fator = np.where(eh_subprevisao, fator_sub, 1.0)
    custo_base["custo"] = custo_base["erro_abs"] * custo_base["cmo"] * fator

    custo_total = float(custo_base["custo"].sum())
    custo_sub = float(custo_base.loc[eh_subprevisao, "custo"].sum())
    custo_super = float(custo_base.loc[~eh_subprevisao, "custo"].sum())

    return {
        "fator_sub": fator_sub,
        "n_incluida_custo": len(custo_base),
        "n_horas_sub": int(eh_subprevisao.sum()),
        "n_horas_super": int((~eh_subprevisao).sum()),
        "custo_total": custo_total,
        "custo_subprevisao": custo_sub,
        "custo_superprevisao": custo_super,
    }


def calcular_vies_direcional(avaliacao: pd.DataFrame, cmo_horario: pd.Series) -> dict:
    """Viés de direção do erro (ESCOPO.md seção 12f): fração do erro ABSOLUTO
    total (não do custo, não da contagem de horas) que vem de subprevisão vs.
    superprevisão. Um modelo bem calibrado deveria ficar perto de 50/50; um viés
    forte para subprevisão é operacionalmente perigoso mesmo com MAPE bom, porque
    é exatamente a direção que a seção 12f penaliza mais. Mesmo escopo de linhas
    (incluida + CMO disponível) que calcular_custo, para comparar com o mesmo
    denominador usado na métrica de custo."""
    incluida_stat = avaliacao[avaliacao["motivo_exclusao"] == "incluida"].copy()
    incluida_stat["cmo"] = incluida_stat["din_instante"].map(cmo_horario)
    base = incluida_stat[incluida_stat["cmo"].notna()].copy()
    base["erro_abs"] = base["erro"].abs()
    eh_subprevisao = base["erro"] < 0

    erro_abs_total = float(base["erro_abs"].sum())
    erro_abs_sub = float(base.loc[eh_subprevisao, "erro_abs"].sum())
    erro_abs_super = float(base.loc[~eh_subprevisao, "erro_abs"].sum())

    return {
        "n_horas_sub": int(eh_subprevisao.sum()),
        "n_horas_super": int((~eh_subprevisao).sum()),
        "pct_erro_abs_subprevisao": erro_abs_sub / erro_abs_total * 100 if erro_abs_total else float("nan"),
        "pct_erro_abs_superprevisao": erro_abs_super / erro_abs_total * 100 if erro_abs_total else float("nan"),
    }


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
    print(f"\nDenominador 1 do MASE (Hyndman padrão): MAE do naive-1-passo (lag=1h) IN-SAMPLE no treino "
          f"(din_instante < {INICIO_AVALIACAO.date()}), {n_pares_treino} pares válidos = {mae_insample_naive1:.4f}")
    print("ATENÇÃO: este denominador é de 1 HORA à frente (persistência simples), não é o horizonte")
    print("day-ahead nem sazonal — é a definição padrão de Hyndman, não recalibrada para o horizonte")
    print("avaliado aqui. Séries horárias de carga têm forte autocorrelação hora-a-hora, então o")
    print("denominador tende a ser pequeno e o MASE dos naives day-ahead tende a ficar > 1 — não é bug.")

    mae_insample_naive_sazonal, n_pares_treino_sazonal = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)
    print(f"\nDenominador 2 do MASE (naive sazonal semanal, lag=168h) IN-SAMPLE no treino "
          f"(din_instante < {INICIO_AVALIACAO.date()}), {n_pares_treino_sazonal} pares válidos = {mae_insample_naive_sazonal:.4f}")
    print("Convenção da literatura de STLF e base de comparação com Simeone (2026, MASE~0,31, denom naive sazonal).")

    modelos = {
        "naive_semanal (REGUA, lag_168h)": previsor_naive(168),
        "naive_diario (referência, lag_24h)": previsor_naive(24),
    }

    resultados = {}
    for nome, previsor in modelos.items():
        print(f"\n=== {nome} ===")
        previsto = rodar_walkforward(serie_alvo, origens, previsor)
        resultado = avaliar_modelo(df, previsto, mae_insample_naive1, mae_insample_naive_sazonal)
        resultados[nome] = resultado

        print(f"Horas-alvo totais no período: {resultado['n_total']}")
        for motivo, n in sorted(resultado["contagem_exclusao"].items()):
            print(f"  {motivo}: {n}")
        print(f"Horas incluídas na métrica estatística: {resultado['n_incluida']}")
        print(f"MAPE: {resultado['mape']:.4f}%")
        print(f"RMSE: {resultado['rmse']:.4f} MWh/h")
        print(f"MAE:  {resultado['mae']:.4f} MWh/h")
        print(f"MASE (denom naive-1passo):  {resultado['mase_naive1']:.4f}")
        print(f"MASE (denom naive-sazonal): {resultado['mase_sazonal']:.4f}")

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
    print("\n=== CONFIRMAÇÃO: modelos dão números diferentes ===")
    print(f"MAE {nomes[0]}: {mae_a:.6f}")
    print(f"MAE {nomes[1]}: {mae_b:.6f}")
    if valores_equivalentes(mae_a, mae_b, rtol=1e-9, atol=1e-9):
        raise SanityCheckError(
            f"MAE de {nomes[0]} e {nomes[1]} são idênticos ({mae_a} == {mae_b}) — "
            "isso indicaria um bug (os dois lags deveriam produzir previsões diferentes)."
        )
    print("OK — os dois modelos produzem previsões diferentes, como esperado (lags diferentes).")

    # --- MASE(denom sazonal) do naive semanal deve ficar ~1,0 por construção
    # (numerador e denominador usam o mesmo lag=168h; a diferença é só treino
    # in-sample vs. avaliação out-of-sample 2024+, então não é exatamente 1,0)
    nome_semanal = nomes[0] if "semanal" in nomes[0] else nomes[1]
    mase_semanal_sazonal = resultados[nome_semanal]["mase_sazonal"]
    print(f"\nMASE (denom naive-sazonal) do {nome_semanal}: {mase_semanal_sazonal:.4f} "
          f"({'~1,0 confirmado' if abs(mase_semanal_sazonal - 1.0) < 0.15 else 'ATENÇÃO: não ficou perto de 1,0'})")

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
        print("Não vou baixar nada nem extrapolar/inventar CMO para os anos ausentes.")
    else:
        cmo_horario = carregar_cmo_horario_se(cobertura["anos_presentes"])
        print(f"CMO horário do SE carregado: {len(cmo_horario)} horas, "
              f"{cmo_horario.index.min()} a {cmo_horario.index.max()}.")

        custos = {}
        for nome in nomes:
            custo = calcular_custo(resultados[nome]["avaliacao"], cmo_horario)
            custos[nome] = custo
            print(f"\n--- Custo: {nome} ---")
            print(f"Horas incluídas na métrica estatística: {custo['n_incluida_estatistica']}")
            print(f"Horas sem CMO (excluídas só do custo): {custo['n_sem_cmo']}")
            print(f"Horas incluídas na métrica de custo: {custo['n_incluida_custo']}")
            print(f"Custo total do período: R$ {custo['custo_total']:,.2f}")
            print(f"Custo médio por hora: R$ {custo['custo_medio_hora']:,.4f}")
            print(f"Limiar do decil 90 do CMO horário: {custo['limiar_p90_cmo']:.4f} R$/MWh "
                  f"({custo['n_horas_top10pct_cmo']} horas)")
            print(f"% do custo total vindo dessas 10% horas de CMO mais alto: {custo['pct_custo_top10pct_cmo']:.4f}%")

        print("\n--- Ranking: erro estatístico (MAE) vs. custo ---")
        ranking_mae = sorted(nomes, key=lambda n: resultados[n]["mae"])
        ranking_custo = sorted(nomes, key=lambda n: custos[n]["custo_total"])
        print(f"Ranking por MAE (melhor->pior): {ranking_mae}")
        print(f"Ranking por custo total (melhor->pior): {ranking_custo}")
        print(f"Rankings coincidem: {'sim' if ranking_mae == ranking_custo else 'não'}")

    print("\nNenhum arquivo .md gerado. Nenhuma conclusão interpretativa — números e contagens acima.")


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
