"""Primeira avaliação completa do Chronos-2 (zero-shot, sem ajuste) no walk-forward
day-ahead. Ver reports/ESCOPO.md seções 9 (Modelos), 11 (Validação), 12 (Métrica),
13 (Incerteza); reports/FACTS.md seção H.

REUSA a estrutura de origem deslizante e as funções de avaliação de
src/modelo_naive.py (gerar_origens, rodar_walkforward, avaliar_modelo,
testar_vazamento, os denominadores de MASE, o custo) — não reimplementa nada disso.
A única coisa nova aqui é o previsor Chronos-2 em si e a checagem de calibração
(P10-P90), que o naive não tem porque é um modelo pontual.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, INICIO_AVALIACAO, N_AMOSTRAS_VAZAMENTO, PROCESSED_DIR,
    SEED_VAZAMENTO, SanityCheckError, avaliar_modelo, calcular_custo,
    calcular_mae_insample_naive1, calcular_mae_insample_naive_sazonal, carregar_cmo_horario_se,
    checar_cobertura_cmo, gerar_origens, previsor_naive, rodar_walkforward, testar_vazamento,
    verificar_grade_regular,
)

CHECKPOINTS = {
    "chronos2_120M": "amazon/chronos-2",
    "chronos2_small_28M": "autogluon/chronos-2-small",
}
CONTEXTOS_HORAS = [96, 256, 512, 1024, 2048]
QUANTIS = [0.05, 0.1, 0.5, 0.9, 0.95]  # P05/P95 adicionados para cobertura a 90% nominal ser reproduzível

# Config vencedora do sweep original (tabela comparativa já comprometida em
# FACTS.md/reports): reproduzida aqui sozinha (não o sweep de 10 combinações) e
# comparada contra estes valores — se divergir, é furo de reprodutibilidade.
ALVO_MODELO = "chronos2_120M"
ALVO_CONTEXTO_H = 2048
ALVO_MASE_SAZONAL = 0.4363
ALVO_MAPE = 1.8235
ALVO_CUSTO_TOTAL = 3_006_870_034.31
TOLERANCIA_PP = 0.001
TOLERANCIA_REL_CUSTO = 0.001

# Cobertura a 90% nominal (P05-P95) calculada no commit 7ce4493 mas nunca
# persistida — citada em 5 documentos (SETUP/technical_report/MODEL_CARD/
# README/one_pager) como 88.9%, sem lastro reprodutível até esta rodada.
ALVO_COBERTURA_90 = 88.9
TOLERANCIA_PP_COBERTURA = 1.0  # pontos percentuais — "divergir materialmente"


def previsor_chronos2(pipeline, contexto_horas: int, cache_quantis: dict):
    """Fábrica de previsor compatível com rodar_walkforward (devolve só a
    mediana — mesmo contrato do naive, reusado sem alteração). Como efeito
    colateral, grava P05/P10/mediana/P90/P95 em cache_quantis[origem]: uma
    chamada ao modelo já devolve todos os quantis, então a calibração (80% E
    90% nominal) não custa nenhuma inferência extra."""
    def prever(historico: pd.Series, origem: pd.Timestamp) -> pd.Series:
        contexto = historico.iloc[-contexto_horas:].to_numpy(dtype="float32")
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        quantis, _ = pipeline.predict_quantiles(
            inputs=[{"target": contexto}], prediction_length=24, quantile_levels=QUANTIS,
        )
        arr = np.asarray(quantis[0][0])  # (24, 5): p05, p10, mediana, p90, p95 — mesma ordem de QUANTIS
        p05, p10, mediana, p90, p95 = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 4]
        cache_quantis[origem] = {"p05": p05, "p10": p10, "mediana": mediana, "p90": p90, "p95": p95}
        return pd.Series(mediana, index=horas_alvo)
    return prever


def montar_calibracao(cache_quantis: dict) -> pd.DataFrame:
    linhas = []
    for origem, d in cache_quantis.items():
        horas = pd.date_range(origem, periods=24, freq="h")
        for h, p05, p10, p90, p95 in zip(horas, d["p05"], d["p10"], d["p90"], d["p95"]):
            linhas.append({"din_instante": h, "p05": p05, "p10": p10, "p90": p90, "p95": p95})
    return pd.DataFrame(linhas)


def calcular_cobertura(avaliacao: pd.DataFrame, calibracao: pd.DataFrame) -> dict:
    incluida = avaliacao[avaliacao["motivo_exclusao"] == "incluida"].copy()
    m = incluida.merge(calibracao, on="din_instante", how="left", validate="one_to_one")
    dentro_80 = (m["real"] >= m["p10"]) & (m["real"] <= m["p90"])
    dentro_90 = (m["real"] >= m["p05"]) & (m["real"] <= m["p95"])
    return {
        "n_avaliado": len(m),
        "cobertura_p10_p90": float(dentro_80.mean()),
        "cobertura_p05_p95": float(dentro_90.mean()),
    }


def verificar_contextos_sem_nan(df: pd.DataFrame, inicio_avaliacao: pd.Timestamp, contexto_max_horas: int) -> int:
    """Confirma, por código, que nenhum contexto usado na varredura toca os 28 NaN
    brutos (todos pré-2019). O alcance mais distante no passado, em toda a
    varredura, é INICIO_AVALIACAO - contexto_max_horas."""
    limite = inicio_avaliacao - pd.Timedelta(hours=contexto_max_horas)
    janela = df[df["din_instante"] >= limite]
    n_nan = int(janela["val_cargaenergiahomwmed"].isna().sum())
    return n_nan


def main():
    if not CARGA_SE_PATH.exists():
        raise SanityCheckError(f"Arquivo ausente: {CARGA_SE_PATH}")

    df = pd.read_parquet(CARGA_SE_PATH)
    df = df.sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)

    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_AVALIACAO)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()
    print(f"Período de avaliação: {INICIO_AVALIACAO.date()} a {fim_serie.date()} — {len(origens)} origens.")

    n_nan_contexto = verificar_contextos_sem_nan(df, INICIO_AVALIACAO, max(CONTEXTOS_HORAS))
    print(f"NaN brutos dentro do alcance de contexto mais distante ({max(CONTEXTOS_HORAS)}h antes de "
          f"{INICIO_AVALIACAO.date()}): {n_nan_contexto}.")
    if n_nan_contexto:
        raise SanityCheckError(
            f"{n_nan_contexto} NaN bruto(s) dentro do alcance de algum contexto — PARANDO para decidir "
            "como o Chronos deve lidar com isso (não testado, não assumido)."
        )
    print("Confirmado: nenhum contexto da varredura toca os 28 NaN brutos (todos pré-2019).")

    mae_insample_naive1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_insample_naive_sazonal, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)
    print(f"\nDenominadores do MASE (mesmos do naive, recalculados aqui pela mesma função): "
          f"naive-1passo={mae_insample_naive1:.4f}, naive-sazonal={mae_insample_naive_sazonal:.4f}")

    cobertura_cmo = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    cmo_horario = None
    if cobertura_cmo["completo"]:
        cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"])
        print(f"CMO horário do SE carregado: {len(cmo_horario)} horas.")
    else:
        print(f"AVISO: CMO incompleto ({cobertura_cmo}) — métrica de custo pulada.")

    # --- baseline naive semanal, recomputado aqui com a MESMA função reusada,
    # para uma linha de comparação 100% consistente com as métricas do Chronos
    print("\n=== Recomputando naive semanal (régua) como baseline nesta mesma tabela ===")
    previsto_naive = rodar_walkforward(serie_alvo, origens, previsor_naive(168))
    resultado_naive = avaliar_modelo(df, previsto_naive, mae_insample_naive1, mae_insample_naive_sazonal)
    custo_naive = calcular_custo(resultado_naive["avaliacao"], cmo_horario) if cmo_horario is not None else None
    linhas_tabela = [{
        "modelo": "naive_semanal (régua)", "contexto_h": 168,
        "mape": resultado_naive["mape"], "rmse": resultado_naive["rmse"],
        "mase_naive1": resultado_naive["mase_naive1"], "mase_sazonal": resultado_naive["mase_sazonal"],
        "custo_total": custo_naive["custo_total"] if custo_naive else None,
        "cobertura_p10_p90": None, "tempo_s": None,
    }]
    print(f"naive semanal: MAPE={resultado_naive['mape']:.4f}% MASE(sazonal)={resultado_naive['mase_sazonal']:.4f}")

    # --- varredura Chronos-2: modelo x contexto
    resultados_completos = {}
    for nome_modelo, checkpoint in CHECKPOINTS.items():
        print(f"\n=== Carregando {nome_modelo} ({checkpoint}) ===")
        t0 = time.time()
        from chronos import BaseChronosPipeline
        pipeline = BaseChronosPipeline.from_pretrained(checkpoint, device_map="cpu")
        print(f"  carregado em {time.time()-t0:.1f}s")

        for contexto_h in CONTEXTOS_HORAS:
            print(f"\n--- {nome_modelo} @ contexto={contexto_h}h ---")
            cache_quantis = {}
            previsor = previsor_chronos2(pipeline, contexto_h, cache_quantis)

            t0 = time.time()
            previsto = rodar_walkforward(serie_alvo, origens, previsor)
            tempo_execucao = time.time() - t0
            print(f"  walk-forward: {len(origens)} origens em {tempo_execucao:.1f}s "
                  f"({tempo_execucao/len(origens)*1000:.1f}ms/origem)")

            resultado = avaliar_modelo(df, previsto, mae_insample_naive1, mae_insample_naive_sazonal)
            resultados_completos[(nome_modelo, contexto_h)] = resultado

            calibracao = montar_calibracao(cache_quantis)
            cobertura = calcular_cobertura(resultado["avaliacao"], calibracao)

            custo = calcular_custo(resultado["avaliacao"], cmo_horario) if cmo_horario is not None else None

            print(f"  MAPE={resultado['mape']:.4f}% RMSE={resultado['rmse']:.2f} "
                  f"MASE(1passo)={resultado['mase_naive1']:.4f} MASE(sazonal)={resultado['mase_sazonal']:.4f} "
                  f"cobertura_P10-P90={cobertura['cobertura_p10_p90']*100:.2f}% "
                  f"custo_total={'R$ %.2f' % custo['custo_total'] if custo else 'N/D'}")

            print(f"  Testando vazamento: {N_AMOSTRAS_VAZAMENTO} origens aleatórias (seed={SEED_VAZAMENTO})...")
            teste = testar_vazamento(serie_alvo, previsto, previsor, f"{nome_modelo}@{contexto_h}h",
                                      N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
            if teste["divergencias"]:
                print(f"  {len(teste['divergencias'])} DIVERGÊNCIA(S) DE VAZAMENTO:", file=sys.stderr)
                for d in teste["divergencias"][:10]:
                    print(f"    - {d}", file=sys.stderr)
                raise SanityCheckError(
                    f"Teste de vazamento falhou para {nome_modelo}@{contexto_h}h: "
                    f"{len(teste['divergencias'])} divergência(s)."
                )
            print(f"  OK — {teste['n_comparacoes']} comparações, 0 divergências.")

            linhas_tabela.append({
                "modelo": nome_modelo, "contexto_h": contexto_h,
                "mape": resultado["mape"], "rmse": resultado["rmse"],
                "mase_naive1": resultado["mase_naive1"], "mase_sazonal": resultado["mase_sazonal"],
                "custo_total": custo["custo_total"] if custo else None,
                "cobertura_p10_p90": cobertura["cobertura_p10_p90"], "tempo_s": tempo_execucao,
            })

        del pipeline

    # --- tabela final
    tabela = pd.DataFrame(linhas_tabela)
    print("\n\n=== TABELA FINAL (modelo x contexto) ===")
    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(tabela.to_string(index=False))

    # --- confirmar que contextos diferentes dao resultados diferentes (por modelo)
    print("\n=== CONFIRMAÇÃO: contextos diferentes dão MAPE diferentes (senão há bug) ===")
    for nome_modelo in CHECKPOINTS:
        sub = tabela[tabela["modelo"] == nome_modelo]
        mapes = sub["mape"].round(6).tolist()
        if len(set(mapes)) == 1:
            raise SanityCheckError(f"{nome_modelo}: todos os 5 contextos deram o MESMO MAPE ({mapes[0]}) — bug.")
        print(f"  {nome_modelo}: {len(set(mapes))} valores distintos de MAPE entre os {len(mapes)} contextos — OK.")

    # --- melhor contexto por modelo (por MASE sazonal, comparável a Simeone)
    print("\n=== MELHOR CONTEXTO POR MODELO (por MASE sazonal) ===")
    melhor_geral = None
    for nome_modelo in CHECKPOINTS:
        sub = tabela[tabela["modelo"] == nome_modelo]
        melhor = sub.loc[sub["mase_sazonal"].idxmin()]
        print(f"  {nome_modelo}: melhor contexto={int(melhor['contexto_h'])}h, "
              f"MASE(sazonal)={melhor['mase_sazonal']:.4f}, MAPE={melhor['mape']:.4f}%")
        if melhor_geral is None or melhor["mase_sazonal"] < melhor_geral["mase_sazonal"]:
            melhor_geral = melhor

    print(f"\nMelhor config geral: {melhor_geral['modelo']} @ {int(melhor_geral['contexto_h'])}h — "
          f"MASE(sazonal)={melhor_geral['mase_sazonal']:.4f}, MAPE={melhor_geral['mape']:.4f}%")
    print(f"naive semanal (régua): MASE(sazonal)={resultado_naive['mase_sazonal']:.4f}, "
          f"MAPE={resultado_naive['mape']:.4f}%")
    if melhor_geral["mase_sazonal"] < resultado_naive["mase_sazonal"]:
        print("-> melhor config do Chronos-2 BATE a régua (naive semanal) neste período/dado.")
    else:
        print("-> melhor config do Chronos-2 NÃO bate a régua (naive semanal) neste período/dado.")

    print("\nMASE(sazonal) do Simeone (2026), ERCOT, contexto 2048h: ~0,31.")
    print("MASE(sazonal) do Chronos-2 aqui, SE/CO, contexto 2048h:")
    for nome_modelo in CHECKPOINTS:
        linha = tabela[(tabela["modelo"] == nome_modelo) & (tabela["contexto_h"] == 2048)].iloc[0]
        print(f"  {nome_modelo}: {linha['mase_sazonal']:.4f}")
    print("NÃO é reprodução do resultado de Simeone — dado diferente (SE/CO vs. ERCOT), "
          "país diferente, quebras estruturais diferentes. É teste no contexto brasileiro.")

    print("\nNenhum arquivo .md gerado. Zero-shot: nenhum fine-tuning, nenhum ajuste de hiperparâmetro.")


def salvar_previsoes_principais():
    """Reproduz e salva a previsão principal do Chronos-2 (config vencedora do
    sweep original de `main()`: chronos2_120M @ 2048h, sem temperatura) — nunca
    tinha sido gravada em disco. Roda SÓ essa config (não o sweep de 10
    combinações), confirma os números contra a tabela comparativa já
    comprometida (FACTS.md) e PARA (SanityCheckError) se algo divergir, em vez
    de gravar um resultado que não bate com o que já foi documentado."""
    if not CARGA_SE_PATH.exists():
        raise SanityCheckError(f"Arquivo ausente: {CARGA_SE_PATH}")

    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)

    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_AVALIACAO)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()
    print(f"Período de avaliação: {INICIO_AVALIACAO.date()} a {fim_serie.date()} — {len(origens)} origens.")
    print(f"Config: {ALVO_MODELO} ({CHECKPOINTS[ALVO_MODELO]}) @ contexto={ALVO_CONTEXTO_H}h, sem temperatura.")

    n_nan_contexto = verificar_contextos_sem_nan(df, INICIO_AVALIACAO, ALVO_CONTEXTO_H)
    if n_nan_contexto:
        raise SanityCheckError(
            f"{n_nan_contexto} NaN bruto(s) dentro do alcance do contexto de {ALVO_CONTEXTO_H}h — PARANDO."
        )
    print(f"Confirmado: contexto de {ALVO_CONTEXTO_H}h não toca NaN bruto.")

    mae_insample_naive1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_insample_naive_sazonal, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)
    print(f"Denominadores do MASE: naive-1passo={mae_insample_naive1:.4f}, "
          f"naive-sazonal={mae_insample_naive_sazonal:.4f}")

    cobertura_cmo = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    cmo_horario = None
    if cobertura_cmo["completo"]:
        cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"])
        print(f"CMO horário do SE carregado: {len(cmo_horario)} horas.")
    else:
        print(f"AVISO: CMO incompleto ({cobertura_cmo}) — métrica de custo pulada.")

    print(f"\n=== Carregando {ALVO_MODELO} ({CHECKPOINTS[ALVO_MODELO]}) ===")
    t0 = time.time()
    from chronos import BaseChronosPipeline
    pipeline = BaseChronosPipeline.from_pretrained(CHECKPOINTS[ALVO_MODELO], device_map="cpu")
    print(f"  carregado em {time.time()-t0:.1f}s")

    cache_quantis = {}
    previsor = previsor_chronos2(pipeline, ALVO_CONTEXTO_H, cache_quantis)

    t0 = time.time()
    previsto = rodar_walkforward(serie_alvo, origens, previsor)
    tempo_execucao = time.time() - t0
    print(f"  walk-forward: {len(origens)} origens em {tempo_execucao:.1f}s "
          f"({tempo_execucao/len(origens)*1000:.1f}ms/origem)")

    resultado = avaliar_modelo(df, previsto, mae_insample_naive1, mae_insample_naive_sazonal)
    calibracao = montar_calibracao(cache_quantis)
    cobertura = calcular_cobertura(resultado["avaliacao"], calibracao)
    custo = calcular_custo(resultado["avaliacao"], cmo_horario) if cmo_horario is not None else None

    print(f"\nMAPE={resultado['mape']:.4f}% RMSE={resultado['rmse']:.2f} "
          f"MASE(1passo)={resultado['mase_naive1']:.4f} MASE(sazonal)={resultado['mase_sazonal']:.4f} "
          f"cobertura_P10-P90(80%nom)={cobertura['cobertura_p10_p90']*100:.2f}% "
          f"cobertura_P05-P95(90%nom)={cobertura['cobertura_p05_p95']*100:.2f}% "
          f"custo_total={'R$ %.2f' % custo['custo_total'] if custo else 'N/D'}")

    print(f"\nTestando vazamento: {N_AMOSTRAS_VAZAMENTO} origens aleatórias (seed={SEED_VAZAMENTO})...")
    teste = testar_vazamento(serie_alvo, previsto, previsor, f"{ALVO_MODELO}@{ALVO_CONTEXTO_H}h",
                              N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
    if teste["divergencias"]:
        print(f"{len(teste['divergencias'])} DIVERGÊNCIA(S) DE VAZAMENTO:", file=sys.stderr)
        for d in teste["divergencias"][:10]:
            print(f"  - {d}", file=sys.stderr)
        raise SanityCheckError(f"Teste de vazamento falhou: {len(teste['divergencias'])} divergência(s).")
    print(f"OK — {teste['n_comparacoes']} comparações, 0 divergências.")

    print("\n=== VERIFICAÇÃO DE REPRODUTIBILIDADE (contra a tabela comparativa já comprometida) ===")
    mase_ok = abs(resultado["mase_sazonal"] - ALVO_MASE_SAZONAL) < TOLERANCIA_PP
    mape_ok = abs(resultado["mape"] - ALVO_MAPE) < TOLERANCIA_PP
    custo_ok = (custo is not None and
                abs(custo["custo_total"] - ALVO_CUSTO_TOTAL) / ALVO_CUSTO_TOTAL < TOLERANCIA_REL_CUSTO)
    cobertura_90_pct = cobertura["cobertura_p05_p95"] * 100
    cobertura90_ok = abs(cobertura_90_pct - ALVO_COBERTURA_90) < TOLERANCIA_PP_COBERTURA
    print(f"  MASE(sazonal): obtido={resultado['mase_sazonal']:.4f} alvo={ALVO_MASE_SAZONAL} -> "
          f"{'OK' if mase_ok else 'DIVERGIU'}")
    print(f"  MAPE: obtido={resultado['mape']:.4f}% alvo={ALVO_MAPE}% -> {'OK' if mape_ok else 'DIVERGIU'}")
    if custo is not None:
        print(f"  Custo total: obtido=R$ {custo['custo_total']:,.2f} alvo=R$ {ALVO_CUSTO_TOTAL:,.2f} -> "
              f"{'OK' if custo_ok else 'DIVERGIU'}")
    print(f"  Cobertura P05-P95 (90% nominal): obtido={cobertura_90_pct:.2f}% alvo~{ALVO_COBERTURA_90}% "
          f"(citado em 5 documentos, commit 7ce4493, nunca antes reproduzível) -> "
          f"{'OK' if cobertura90_ok else 'DIVERGIU'}")
    if not (mase_ok and mape_ok and custo_ok):
        raise SanityCheckError(
            "Números do Chronos-2 divergem da tabela original comprometida (FACTS.md) — seria furo de "
            "reprodutibilidade que precisamos entender antes de documentar. PARANDO."
        )
    if not cobertura90_ok:
        raise SanityCheckError(
            f"Cobertura P05-P95 recomputada ({cobertura_90_pct:.2f}%) diverge materialmente dos ~88.9% "
            "citados em SETUP.md/technical_report.md/MODEL_CARD.md/README.md/one_pager.md (commit 7ce4493) "
            "— os documentos precisariam ser corrigidos, não este número. PARANDO para reportar."
        )
    print("Confirmado: bate com os números já documentados, incluindo a cobertura de 90% agora "
          "reproduzível. Reprodutibilidade OK.")

    export = previsto.merge(calibracao, on="din_instante", how="left", validate="one_to_one")
    export["origem"] = export["din_instante"].dt.normalize()
    export["modelo"] = ALVO_MODELO
    export["contexto_h"] = ALVO_CONTEXTO_H
    export = export[["origem", "din_instante", "previsto", "p05", "p10", "p90", "p95", "modelo", "contexto_h"]]
    out_path = PROCESSED_DIR / "chronos_previsoes.parquet"
    export.to_parquet(out_path, index=False)
    print(f"\nPrevisões principais salvas em {out_path} ({len(export)} linhas, colunas: {list(export.columns)}).")


if __name__ == "__main__":
    try:
        salvar_previsoes_principais()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
