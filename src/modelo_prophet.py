"""Prophet — baseline clássico, grupo de controle da extensão (1) do escopo (ver
reports/ESCOPO.md seções 9, 11, 12, 13). Ao contrário do SARIMA (satura, contexto
curto), o Prophet USA histórico longo para estimar tendência e sazonalidade anual
— por isso o contexto aqui é de 2 anos, uma decisão de método, não de orçamento.

Sazonalidades: diária, semanal, anual (Fourier padrão do Prophet). Feriados: usa a
feature `is_feriado` já existente (calcular_is_feriado, mesma função de
gerar_features.py) como regressor extra, em vez do `add_country_holidays` nativo do
Prophet — para manter uma única definição de feriado no projeto inteiro (a mesma
biblioteca `holidays`, a mesma chamada), não duas fontes divergentes. dst_ativo
também entra como regressor extra — mesma decisão do SARIMA.

Temperatura NÃO é passada (camada secundária, fora do modelo principal — FACTS.md
seção H).

Intervalos: a mediana (previsão pontual) vem de `predict()["yhat"]` —
DETERMINÍSTICO dado seed fixa (ver nota abaixo) — e não de `predictive_samples()`.
P10/P90 (80% nominal) vêm de `predict()["yhat_lower"/"yhat_upper"]`, que também são
determinísticos (Prophet usa `interval_width=0.80` por padrão para essas colunas —
mesmo cálculo interno do `predict()`, sem amostragem extra). Só P05/P95 (90%
nominal) ainda vêm de `predictive_samples()` (1000 trajetórias) — aceitável porque
essas bordas alimentam só a estatística agregada de cobertura, nunca o ponto usado
no MAPE/MASE/custo nem no teste de vazamento.

Reusa gerar_origens, rodar_walkforward, avaliar_modelo, testar_vazamento,
calcular_mae_insample_naive1/sazonal, checar_cobertura_cmo, carregar_cmo_horario_se,
calcular_custo de src/modelo_naive.py — não reimplementa nada disso.

NOTA SOBRE DETERMINISMO E O TESTE DE VAZAMENTO (histórico, commits f87138a ->
fb62833 -> 1c296f9): a primeira rodada completa (commit f87138a) usava
`predictive_samples()` também para a mediana e reportou 720/720 "divergências" no
teste de vazamento. Duas causas distintas, ambas diagnosticadas e provadas (não
supostas):
(1) não-determinismo numérico do otimizador Stan/L-BFGS (threading de BLAS/OpenMP,
    sem seed fixa) — PROVADO em src/verificar_determinismo_prophet.py: com
    STAN_NUM_THREADS/OMP_NUM_THREADS/MKL_NUM_THREADS/OPENBLAS_NUM_THREADS/
    NUMEXPR_NUM_THREADS/VECLIB_MAXIMUM_THREADS=1 e seed fixa em `Prophet.fit(...,
    seed=...)`, 0/720 divergências.
(2) `predictive_samples()` sorteia ruído de incerteza numa fonte aleatória própria
    que a seed do fit não controla — PROVADO em
    src/verificar_vazamento_prophet_temp_predict.py: `predict()["yhat"]` é bit-
    idêntico entre chamadas repetidas; a mediana de `predictive_samples()` não é.
Esta rodada (commit de "salvar previsões principais") corrige as duas: single-
thread forçado logo no topo do módulo, seed fixa no fit, e mediana via `predict()`.
Salva incrementalmente (a cada N_INCREMENTO origens) em data/processed/
prophet_previsoes.parquet — retomável se a rodada (~3h, dominada pelo Prophet) for
interrompida.
"""
import os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "STAN_NUM_THREADS"):
    os.environ[_var] = "1"

import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_features import calcular_dst_ativo, calcular_is_feriado  # noqa: E402
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, INICIO_AVALIACAO, N_AMOSTRAS_VAZAMENTO, PROCESSED_DIR, SEED_VAZAMENTO,
    SanityCheckError, avaliar_modelo, calcular_custo, calcular_mae_insample_naive1,
    calcular_mae_insample_naive_sazonal, carregar_cmo_horario_se, checar_cobertura_cmo,
    gerar_origens, testar_vazamento, verificar_grade_regular,
)

CONTEXTO_H = 17520  # 2 anos — decisão de método (tendência/sazonalidade anual)
SEED_STAN = 42
N_INCREMENTO = 50
OUT_PATH = PROCESSED_DIR / "prophet_previsoes.parquet"

# Números da tabela comparativa já comprometida (commit f87138a, reconfirmados
# nas sanidades seguintes) — se a rodada com predict() divergir de forma
# relevante, é furo de reprodutibilidade, não um novo resultado.
ALVO_MASE_SAZONAL = 1.1678
ALVO_MAPE = 4.9985
ALVO_CUSTO_TOTAL = 7_863_385_780.72
TOLERANCIA_PP = 0.05  # mediana muda de predictive_samples() para predict() — folga maior que a do Chronos
TOLERANCIA_REL_CUSTO = 0.02


def previsor_prophet(contexto_horas: int, cache: dict):
    from prophet import Prophet

    def prever(historico: pd.Series, origem: pd.Timestamp) -> pd.Series:
        contexto = historico.iloc[-contexto_horas:]
        horas_alvo = pd.date_range(origem, periods=24, freq="h")

        train = pd.DataFrame({"ds": contexto.index, "y": contexto.values})
        train["dst_ativo"] = calcular_dst_ativo(train["ds"]).astype(float).values
        train["is_feriado"] = calcular_is_feriado(train["ds"]).astype(float).values

        m = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=True)
        m.add_regressor("dst_ativo")
        m.add_regressor("is_feriado")
        m.fit(train, seed=SEED_STAN)

        futuro = pd.DataFrame({"ds": horas_alvo})
        futuro["dst_ativo"] = calcular_dst_ativo(futuro["ds"]).astype(float).values
        futuro["is_feriado"] = calcular_is_feriado(futuro["ds"]).astype(float).values

        prev = m.predict(futuro)  # DETERMINÍSTICO — mediana e P10/P90 (interval_width=0.80 padrão)
        p10, mediana, p90 = prev["yhat_lower"].values, prev["yhat"].values, prev["yhat_upper"].values

        amostras = m.predictive_samples(futuro)["yhat"]  # só para P05/P95 — não usado no ponto
        p05, p95 = np.percentile(amostras, [5, 95], axis=1)

        cache[origem] = {"p05": p05, "p10": p10, "p90": p90, "p95": p95}
        return pd.Series(mediana, index=horas_alvo)
    return prever


def rodar_incremental(previsor, serie_alvo: pd.Series, origens: list, cache: dict, out_path: Path) -> pd.DataFrame:
    """Mesmo truncamento de rodar_walkforward (searchsorted), mas salva
    incrementalmente a cada N_INCREMENTO origens — retomável se a rodada estourar."""
    linhas = []
    t_inicio = time.time()
    for i, origem in enumerate(origens):
        idx_corte = serie_alvo.index.searchsorted(origem)
        historico = serie_alvo.iloc[:idx_corte]
        if len(historico) and historico.index[-1] >= origem:
            raise SanityCheckError(f"Corte malformado: histórico até {origem} contém {historico.index[-1]}.")

        previsao = previsor(historico, origem)
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        if not previsao.index.equals(horas_alvo):
            raise SanityCheckError(f"previsor não devolveu as 24 horas esperadas para origem {origem}.")

        d = cache[origem]
        for j, h in enumerate(horas_alvo):
            linhas.append({
                "din_instante": h, "origem": origem, "previsto": float(previsao[h]),
                "p05": d["p05"][j], "p10": d["p10"][j], "p90": d["p90"][j], "p95": d["p95"][j],
            })

        if (i + 1) % N_INCREMENTO == 0 or i == len(origens) - 1:
            pd.DataFrame(linhas).to_parquet(out_path, index=False)
            decorrido = time.time() - t_inicio
            print(f"  progresso: {i+1}/{len(origens)} origens ({decorrido/60:.1f} min decorridos, "
                  f"{decorrido/(i+1):.2f}s/origem) — salvo em {out_path}", flush=True)

    return pd.DataFrame(linhas)


def main():
    if not CARGA_SE_PATH.exists():
        raise SanityCheckError(f"Arquivo ausente: {CARGA_SE_PATH}")

    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_AVALIACAO)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()
    print(f"Período: {INICIO_AVALIACAO.date()} a {fim_serie.date()} — {len(origens)} origens. "
          f"Prophet, contexto={CONTEXTO_H}h ({CONTEXTO_H//8760} anos), regressores=dst_ativo+is_feriado, "
          f"mediana via predict() (determinístico), seed do Stan={SEED_STAN}, single-thread forçado.")

    mae1, _ = calcular_mae_insample_naive1(df, INICIO_AVALIACAO)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_AVALIACAO, 168)

    cobertura_cmo = checar_cobertura_cmo(INICIO_AVALIACAO.year, fim_serie.year)
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"]) if cobertura_cmo["completo"] else None
    if cmo_horario is None:
        print(f"AVISO: CMO incompleto ({cobertura_cmo}) — métrica de custo pulada.")

    cache = {}
    previsor = previsor_prophet(CONTEXTO_H, cache)

    t0 = time.time()
    resultados_df = rodar_incremental(previsor, serie_alvo, origens, cache, OUT_PATH)
    tempo_execucao = time.time() - t0
    print(f"walk-forward: {len(origens)} origens em {tempo_execucao:.1f}s ({tempo_execucao/60:.1f} min, "
          f"{tempo_execucao/len(origens)*1000:.1f}ms/origem)")

    previsto = resultados_df[["din_instante", "previsto"]].drop_duplicates("din_instante")
    resultado = avaliar_modelo(df, previsto, mae1, mae_saz)

    aval = resultado["avaliacao"].merge(
        resultados_df[["din_instante", "p05", "p10", "p90", "p95"]], on="din_instante", how="left")
    incluida = aval[aval["motivo_exclusao"] == "incluida"]
    cobertura_80 = float(((incluida["real"] >= incluida["p10"]) & (incluida["real"] <= incluida["p90"])).mean())
    cobertura_90 = float(((incluida["real"] >= incluida["p05"]) & (incluida["real"] <= incluida["p95"])).mean())

    custo = calcular_custo(resultado["avaliacao"], cmo_horario) if cmo_horario is not None else None

    print(f"\nMAPE={resultado['mape']:.4f}% RMSE={resultado['rmse']:.2f} "
          f"MASE(1passo)={resultado['mase_naive1']:.4f} MASE(sazonal)={resultado['mase_sazonal']:.4f}")
    print(f"Cobertura 80%: {cobertura_80*100:.2f}% | Cobertura 90%: {cobertura_90*100:.2f}%")
    print(f"Custo total: R$ {custo['custo_total']:,.2f}" if custo else "Custo: N/D (CMO incompleto)")

    print(f"\nTestando vazamento: {N_AMOSTRAS_VAZAMENTO} origens aleatórias (seed={SEED_VAZAMENTO})...")
    teste = testar_vazamento(serie_alvo, previsto, previsor, "Prophet", N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
    if teste["divergencias"]:
        print(f"{len(teste['divergencias'])} DIVERGÊNCIA(S):", file=sys.stderr)
        for d_ in teste["divergencias"][:10]:
            print(f"  - {d_}", file=sys.stderr)
        raise SanityCheckError("Teste de vazamento falhou para Prophet.")
    print(f"OK — {teste['n_comparacoes']} comparações, 0 divergências.")

    print("\n=== VERIFICAÇÃO DE REPRODUTIBILIDADE (contra a tabela comparativa já comprometida, commit f87138a) ===")
    mase_ok = abs(resultado["mase_sazonal"] - ALVO_MASE_SAZONAL) < TOLERANCIA_PP
    mape_ok = abs(resultado["mape"] - ALVO_MAPE) < TOLERANCIA_PP
    custo_ok = (custo is not None and
                abs(custo["custo_total"] - ALVO_CUSTO_TOTAL) / ALVO_CUSTO_TOTAL < TOLERANCIA_REL_CUSTO)
    print(f"  MASE(sazonal): obtido={resultado['mase_sazonal']:.4f} alvo={ALVO_MASE_SAZONAL} -> "
          f"{'OK' if mase_ok else 'DIVERGIU'}")
    print(f"  MAPE: obtido={resultado['mape']:.4f}% alvo={ALVO_MAPE}% -> {'OK' if mape_ok else 'DIVERGIU'}")
    if custo is not None:
        print(f"  Custo total: obtido=R$ {custo['custo_total']:,.2f} alvo=R$ {ALVO_CUSTO_TOTAL:,.2f} -> "
              f"{'OK' if custo_ok else 'DIVERGIU'}")
    if not (mase_ok and mape_ok and custo_ok):
        raise SanityCheckError(
            "Números do Prophet divergem da tabela original comprometida (FACTS.md/commit f87138a) — seria "
            "furo de reprodutibilidade que precisamos entender antes de documentar. PARANDO."
        )
    print("Confirmado: bate com os números já documentados (dentro da folga esperada pela troca de "
          "predictive_samples() para predict() na mediana). Reprodutibilidade OK.")

    print(f"\nPrevisões principais (já salvas incrementalmente durante o walk-forward) confirmadas em {OUT_PATH} "
          f"({len(resultados_df)} linhas).")

    print("\n=== RESUMO_PROPHET_JSON ===")
    import json
    print(json.dumps({
        "modelo": "Prophet(d+w+y,dst,feriado)", "contexto_h": CONTEXTO_H,
        "mape": resultado["mape"], "rmse": resultado["rmse"],
        "mase_naive1": resultado["mase_naive1"], "mase_sazonal": resultado["mase_sazonal"],
        "custo_total": custo["custo_total"] if custo else None,
        "cobertura_80": cobertura_80, "cobertura_90": cobertura_90,
        "tempo_s": tempo_execucao,
    }))


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
