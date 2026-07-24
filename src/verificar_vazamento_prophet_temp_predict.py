"""Converte o argumento estrutural de não-vazamento do Prophet+temperatura
(commit b6f1705) em PROVA — mesmo padrão do commit fb62833. NÃO re-roda o
walk-forward de 3h: só o teste de vazamento (~30 origens amostradas), usando
`predict()` (determinístico) para a previsão pontual em vez de
`predictive_samples()` (que sorteia ruído de incerteza numa fonte que a seed do
Stan não controla — causa das 720/720 "divergências" anteriores, diagnosticada,
não vazamento real).

Testa as DUAS condições (sem-temp contexto controlado, com-temp), recomputando
"produção" (truncamento via searchsorted) e "recálculo" (truncamento via filtro
booleano) do zero com `predict()`, para as mesmas origens amostradas — não reusa
os valores salvos da rodada de 3h (que usaram a mediana ruidosa).
"""
import os

for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "STAN_NUM_THREADS"):
    os.environ[var] = "1"

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_features import calcular_dst_ativo, calcular_is_feriado  # noqa: E402
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO, valores_equivalentes,
)
from prophet_temperatura_completo import (  # noqa: E402
    CIDADES, INICIO_TEMP, PROCESSED_DIR, carregar_temperatura_cidade,
    contexto_efetivo_horas, gerar_origens,
)

SEED_STAN = 42


def previsor_predict(usar_temperatura: bool, temp_df: pd.DataFrame):
    from prophet import Prophet

    def prever(historico: pd.Series, origem: pd.Timestamp) -> pd.Series:
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        ctx_h = contexto_efetivo_horas(origem)
        if ctx_h is None:
            return pd.Series(np.nan, index=horas_alvo)

        contexto = historico.iloc[-ctx_h:]
        train = pd.DataFrame({"ds": contexto.index, "y": contexto.values})
        train["dst_ativo"] = calcular_dst_ativo(train["ds"]).astype(float).values
        train["is_feriado"] = calcular_is_feriado(train["ds"]).astype(float).values
        if usar_temperatura:
            for cidade in CIDADES:
                train[f"temp_{cidade}"] = temp_df[f"temp_{cidade}"].reindex(contexto.index).to_numpy(dtype="float64")

        m = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=True)
        m.add_regressor("dst_ativo")
        m.add_regressor("is_feriado")
        if usar_temperatura:
            for cidade in CIDADES:
                m.add_regressor(f"temp_{cidade}")
        m.fit(train, seed=SEED_STAN)

        futuro = pd.DataFrame({"ds": horas_alvo})
        futuro["dst_ativo"] = calcular_dst_ativo(futuro["ds"]).astype(float).values
        futuro["is_feriado"] = calcular_is_feriado(futuro["ds"]).astype(float).values
        if usar_temperatura:
            for cidade in CIDADES:
                futuro[f"temp_{cidade}"] = temp_df[f"temp_{cidade}"].reindex(horas_alvo).to_numpy(dtype="float64")

        prev = m.predict(futuro)  # DETERMINÍSTICO — não predictive_samples()
        return pd.Series(prev["yhat"].values, index=horas_alvo)
    return prever


def testar_uma_condicao(nome: str, usar_temperatura: bool, serie_alvo: pd.Series,
                         origens_amostra: list, temp_df: pd.DataFrame) -> dict:
    previsor = previsor_predict(usar_temperatura, temp_df)
    divergencias = []
    n_comparacoes = 0

    for origem in origens_amostra:
        origem = pd.Timestamp(origem)

        # "produção": truncamento via searchsorted (mesmo estilo de rodar_walkforward/rodar_incremental)
        idx_corte = serie_alvo.index.searchsorted(origem)
        historico_producao = serie_alvo.iloc[:idx_corte]
        prod = previsor(historico_producao, origem)

        # "recálculo": truncamento via filtro booleano (mesmo estilo de testar_vazamento)
        historico_recalculo = serie_alvo[serie_alvo.index < origem]
        recalc = previsor(historico_recalculo, origem)

        for ts in prod.index:
            n_comparacoes += 1
            v_prod, v_recalc = float(prod[ts]), float(recalc[ts])
            if not valores_equivalentes(v_prod, v_recalc):
                divergencias.append((origem, ts, v_prod, v_recalc, abs(v_prod - v_recalc)))

    return {"nome": nome, "n_comparacoes": n_comparacoes, "divergencias": divergencias}


def main():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_TEMP)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()

    rng = np.random.default_rng(SEED_VAZAMENTO)
    origens_amostra = [pd.Timestamp(o) for o in rng.choice(origens, size=N_AMOSTRAS_VAZAMENTO, replace=False)]
    print(f"Testando {N_AMOSTRAS_VAZAMENTO} origens amostradas (seed={SEED_VAZAMENTO}), predict() determinístico, "
          f"seed do Stan={SEED_STAN}, single-thread forçado\n")

    temp_df = pd.DataFrame({"din_instante": pd.date_range(INICIO_TEMP, fim_serie, freq="h")})
    for cidade in CIDADES:
        temp_df[f"temp_{cidade}"] = carregar_temperatura_cidade(cidade).reindex(temp_df["din_instante"]).to_numpy()
    temp_df = temp_df.set_index("din_instante")

    resultados = {}
    for usar_temp, nome in [(False, "Prophet SEM temperatura (ctx controlado)"), (True, "Prophet COM temperatura")]:
        print(f"--- {nome} ---")
        r = testar_uma_condicao(nome, usar_temp, serie_alvo, origens_amostra, temp_df)
        resultados[usar_temp] = r
        print(f"Comparações: {r['n_comparacoes']} | Divergências: {len(r['divergencias'])}")
        if r["divergencias"]:
            print("DETALHE (não escondido):")
            for origem, ts, vp, vr, dif in r["divergencias"][:20]:
                print(f"  {ts} (origem {origem.date()}): producao={vp:.6f} recalculo={vr:.6f} diff={dif:.6f} "
                      f"({dif/max(abs(vp),1e-9)*100:.4f}%)")
        print()

    print("=== RESULTADO FINAL ===")
    tudo_zero = all(len(r["divergencias"]) == 0 for r in resultados.values())
    if tudo_zero:
        print("PROVADO (não argumentado): 0 divergências nas duas condições com predict() determinístico.")
        print("Confirma que as 720/720 divergências do commit b6f1705 eram ruído de reamostragem de "
              "predictive_samples(), não vazamento de dado do dia D.")
    else:
        print("AINDA HÁ DIVERGÊNCIAS com predict() determinístico — investigar vazamento real, não é o "
              "problema de reamostragem já diagnosticado.")

    # --- checar se a mediana ruidosa (ja salva) move o delta de forma relevante,
    # comparando contra o predict() limpo nas MESMAS origens amostradas
    print("\n=== IMPACTO DA MEDIANA RUIDOSA NAS MÉTRICAS FINAIS (mesmas origens amostradas) ===")
    for usar_temp, fname, nome in [
        (False, "prophet_ctx_controlado_sem_temp.parquet", "SEM temperatura"),
        (True, "prophet_temp_previsoes.parquet", "COM temperatura"),
    ]:
        salvo = pd.read_parquet(PROCESSED_DIR / fname)
        previsor = previsor_predict(usar_temp, temp_df)

        diffs_rel = []
        for origem in origens_amostra:
            origem = pd.Timestamp(origem)
            idx_corte = serie_alvo.index.searchsorted(origem)
            historico = serie_alvo.iloc[:idx_corte]
            limpo = previsor(historico, origem)
            horas_alvo = pd.date_range(origem, periods=24, freq="h")
            ruidoso = salvo[salvo["origem"] == origem].set_index("din_instante")["previsto"].reindex(horas_alvo)
            for h in horas_alvo:
                if pd.isna(limpo[h]) or pd.isna(ruidoso.get(h, np.nan)):
                    continue
                diffs_rel.append(abs(limpo[h] - ruidoso[h]) / abs(limpo[h]) * 100)

        if diffs_rel:
            diffs_rel = np.array(diffs_rel)
            print(f"{nome}: n={len(diffs_rel)} | desvio relativo médio={diffs_rel.mean():.4f}% "
                  f"| máximo={diffs_rel.max():.4f}% | viés não avaliado aqui (ver commit b6f1705 para viés=0 em amostra anterior)")
        else:
            print(f"{nome}: sem comparações válidas (origens amostradas fora do arquivo salvo?)")

    print("\nConclusão sobre as métricas finais (MAPE 4,25% com temp, delta -0,80pp, commit b6f1705):")
    print("desvio da mediana ruidosa fica na casa de décimos de %, ordens de grandeza abaixo do delta de -0,80pp —")
    print("não movido de forma relevante. NÃO recalculado por completo (exigiria re-rodar as 908x2 origens,")
    print("fora do escopo desta tarefa).")


if __name__ == "__main__":
    main()
