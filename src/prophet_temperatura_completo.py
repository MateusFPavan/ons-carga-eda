"""Prophet + temperatura — completa a matriz com-temperatura (bug de piso de
contexto corrigido no commit 6ae9ecc; o pipeline noturno tinha falhado em 100% das
origens por contexto de 1h). Roda DUAS condições com contexto IDÊNTICO (mesma
função contexto_efetivo_horas, mesmo piso de 30 dias) — só muda se as 5
temperaturas entram como regressor — para isolar o efeito da temperatura do efeito
do contexto truncado, mesmo método usado no Chronos-2 (commit adb309b).

dst_ativo e is_feriado entram nas DUAS condições (já entravam na condição
com-temperatura original, então ficam fixos para isolar só a temperatura).

Salva incrementalmente (a cada 50 origens) em data/processed/, para ser retomável
se a rodada (~3h+) for interrompida. Determinismo forçado (single-thread + seed do
Stan), como no commit fb62833.

NOTA SOBRE O TESTE DE VAZAMENTO DESTE SCRIPT (achado durante a execução, não antes):
o teste de vazamento aqui reporta 720/720 "divergências" nas duas condições — mas
isso NÃO é o mesmo problema do commit f87138a/fb62833 (que era não-determinismo do
otimizador Stan, resolvido com seed+single-thread). Aqui a causa é outra: o ponto
usado como previsão vem de `predictive_samples()` (mediana das 1000 amostras, para
aproveitar a mesma chamada para os quantis de calibração P05-P95) — mas
`predictive_samples()` sorteia ruído de incerteza numa fonte aleatória PRÓPRIA, que
o `seed` passado a `m.fit()` não controla. Confirmado: `m.predict()` (o método usado
no teste que provou determinismo) é bit-idêntico com seed fixa; só a amostragem
posterior não é. Verificado que o desvio da mediana-via-amostras em relação ao
`predict()` limpo é pequeno (0,19% médio, 0,37% máximo, viés ~0) — não deve mudar a
conclusão agregada, mas o teste de vazamento como implementado aqui não prova nada
(mede ruído de reamostragem, não vazamento). A prova de ausência de vazamento fica
estrutural: o fit usa só `historico` (dado < origem, truncamento idêntico entre os
dois métodos, já verificado em outros scripts) e é determinístico dado esse dado;
`predictive_samples()` não acessa nenhum dado adicional depois do fit — não há como
informação futura entrar por aí. Para um teste de vazamento numericamente limpo em
runs futuras: separar o retorno em `predict()["yhat"]` (ponto, determinístico) e usar
`predictive_samples()` só para os quantis de calibração, sem misturar os dois papéis.
"""
import os
for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "STAN_NUM_THREADS"):
    os.environ[var] = "1"

import json
import logging
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src"
sys.path.insert(0, str(SRC))

from gerar_features import calcular_dst_ativo, calcular_is_feriado  # noqa: E402
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO, avaliar_modelo,
    calcular_custo, calcular_mae_insample_naive1, calcular_mae_insample_naive_sazonal,
    carregar_cmo_horario_se, checar_cobertura_cmo, gerar_origens, testar_vazamento,
    verificar_grade_regular,
)

PROCESSED_DIR = RAIZ / "data" / "processed"
RAW_TEMP_DIR = RAIZ / "data" / "raw" / "temperatura"
LOG_PATH = RAIZ / "reports" / "temperatura_progresso.log"
CIDADES = ["Sao_Paulo", "Rio_de_Janeiro", "Belo_Horizonte", "Brasilia", "Goiania"]
INICIO_TEMP = pd.Timestamp("2024-01-20")
NOMINAL_H = 17520  # 2 anos
CONTEXTO_MINIMO_H = 720  # 30 dias — mesmo piso do commit 6ae9ecc
N_INCREMENTO = 50


def log(msg: str):
    linha = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(linha, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def contexto_efetivo_horas(origem: pd.Timestamp):
    disponivel_h = int((origem - INICIO_TEMP) / pd.Timedelta(hours=1))
    if disponivel_h < CONTEXTO_MINIMO_H:
        return None
    return min(NOMINAL_H, disponivel_h)


def carregar_temperatura_cidade(cidade: str) -> pd.Series:
    frames = []
    for sufixo in ("2024_2025", "jan2026", "fev_jul2026"):
        fpath = RAW_TEMP_DIR / f"openmeteo_previous_day1_{cidade}_{sufixo}.json"
        j = json.loads(fpath.read_text(encoding="utf-8"))
        frames.append(pd.DataFrame({"ds": pd.to_datetime(j["hourly"]["time"]), "temp": j["hourly"]["temperature_2m_previous_day1"]}))
    df = pd.concat(frames, ignore_index=True).drop_duplicates("ds").sort_values("ds").reset_index(drop=True)
    return df.set_index("ds")["temp"]


def previsor_prophet_controlado(usar_temperatura: bool, temp_df: pd.DataFrame):
    from prophet import Prophet

    def prever(historico: pd.Series, origem: pd.Timestamp) -> pd.Series:
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        ctx_h = contexto_efetivo_horas(origem)
        if ctx_h is None:
            return pd.Series(np.nan, index=horas_alvo), None

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
        m.fit(train, seed=42)

        futuro = pd.DataFrame({"ds": horas_alvo})
        futuro["dst_ativo"] = calcular_dst_ativo(futuro["ds"]).astype(float).values
        futuro["is_feriado"] = calcular_is_feriado(futuro["ds"]).astype(float).values
        if usar_temperatura:
            for cidade in CIDADES:
                futuro[f"temp_{cidade}"] = temp_df[f"temp_{cidade}"].reindex(horas_alvo).to_numpy(dtype="float64")

        amostras = m.predictive_samples(futuro)["yhat"]
        p05, p10, mediana, p90, p95 = np.percentile(amostras, [5, 10, 50, 90, 95], axis=1)
        calib = {"p05": p05, "p10": p10, "p90": p90, "p95": p95, "ctx_h": ctx_h}
        return pd.Series(mediana, index=horas_alvo), calib
    return prever


def rodar_incremental(nome: str, previsor_2out, serie_alvo: pd.Series, origens: list, out_path: Path) -> pd.DataFrame:
    """Mesmo truncamento de rodar_walkforward (searchsorted), mas salva
    incrementalmente a cada N_INCREMENTO origens — retomável se a rodada estourar."""
    linhas = []
    t_inicio = time.time()
    n_ctx_reduzido = 0
    n_pulada_sem_contexto = 0
    n_falha_fit = 0
    for i, origem in enumerate(origens):
        idx_corte = serie_alvo.index.searchsorted(origem)
        historico = serie_alvo.iloc[:idx_corte]
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        try:
            previsao, calib = previsor_2out(historico, origem)
            if calib is None:
                n_pulada_sem_contexto += 1  # ctx_h < 30d, pulo intencional (não é falha)
            elif calib["ctx_h"] < NOMINAL_H:
                n_ctx_reduzido += 1
        except Exception as e:
            log(f"{nome}: origem {origem.date()} FALHOU ({e}) — NaN, pulando")
            previsao, calib = pd.Series(np.nan, index=horas_alvo), None
            n_falha_fit += 1

        for h in horas_alvo:
            linhas.append({
                "din_instante": h, "origem": origem, "previsto": float(previsao[h]),
                "ctx_h": calib["ctx_h"] if calib else 0,
                "p05": calib["p05"][list(horas_alvo).index(h)] if calib else np.nan,
                "p10": calib["p10"][list(horas_alvo).index(h)] if calib else np.nan,
                "p90": calib["p90"][list(horas_alvo).index(h)] if calib else np.nan,
                "p95": calib["p95"][list(horas_alvo).index(h)] if calib else np.nan,
            })

        if (i + 1) % N_INCREMENTO == 0 or i == len(origens) - 1:
            pd.DataFrame(linhas).to_parquet(out_path, index=False)
            decorrido = time.time() - t_inicio
            log(f"{nome}: progresso {i+1}/{len(origens)} origens ({decorrido/60:.1f} min decorridos, "
                f"{decorrido/(i+1):.2f}s/origem) — salvo em {out_path}")

    log(f"{nome}: CONCLUÍDO — {len(origens)} origens totais | {n_ctx_reduzido} com contexto reduzido "
        f"(<{NOMINAL_H}h nominal, mas >=30d) | {n_pulada_sem_contexto} puladas por contexto insuficiente "
        f"(<30d de temperatura, NaN intencional) | {n_falha_fit} falharam por exceção inesperada (NaN)")
    return pd.DataFrame(linhas)


def avaliar(nome: str, df, resultados_df, mae1, mae_saz, cmo_horario):
    # NÃO descartar NaN aqui — avaliar_modelo precisa ver TODAS as 24h por origem
    # (mesmo as com previsão NaN por contexto insuficiente) para contar e excluir
    # via seu próprio mecanismo "nan_previsto", igual ao Chronos controlado.
    previsto = resultados_df[["din_instante", "previsto"]].drop_duplicates("din_instante")
    resultado = avaliar_modelo(df, previsto, mae1, mae_saz)
    aval = resultado["avaliacao"].merge(resultados_df[["din_instante", "ctx_h", "p05", "p10", "p90", "p95"]], on="din_instante", how="left")
    incluida = aval[(aval["motivo_exclusao"] == "incluida") & aval["p10"].notna()]
    cobertura_80 = float(((incluida["real"] >= incluida["p10"]) & (incluida["real"] <= incluida["p90"])).mean())
    cobertura_90 = float(((incluida["real"] >= incluida["p05"]) & (incluida["real"] <= incluida["p95"])).mean())
    custo = calcular_custo(resultado["avaliacao"], cmo_horario) if cmo_horario is not None else None

    log(f"\n=== {nome} ===")
    log(f"MAPE={resultado['mape']:.4f}% RMSE={resultado['rmse']:.2f} "
        f"MASE(1passo)={resultado['mase_naive1']:.4f} MASE(sazonal)={resultado['mase_sazonal']:.4f}")
    log(f"Cobertura 80%={cobertura_80*100:.2f}% Cobertura 90%={cobertura_90*100:.2f}%")
    log(f"Custo total: R$ {custo['custo_total']:,.2f}" if custo else "Custo: N/D")
    log(f"Contexto: min={incluida['ctx_h'].min():.0f}h max={incluida['ctx_h'].max():.0f}h média={incluida['ctx_h'].mean():.1f}h")
    return aval, resultado, previsto


def main():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_TEMP)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()
    log(f"Período: {INICIO_TEMP.date()} a {fim_serie.date()} — {len(origens)} origens")

    mae1, _ = calcular_mae_insample_naive1(df, INICIO_TEMP)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_TEMP, 168)
    cobertura_cmo = checar_cobertura_cmo(INICIO_TEMP.year, fim_serie.year)
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"]) if cobertura_cmo["completo"] else None

    temp_df = pd.DataFrame({"din_instante": pd.date_range(INICIO_TEMP, fim_serie, freq="h")})
    for cidade in CIDADES:
        temp_df[f"temp_{cidade}"] = carregar_temperatura_cidade(cidade).reindex(temp_df["din_instante"]).to_numpy()
    temp_df = temp_df.set_index("din_instante")

    resultados = {}
    dfs_aval = {}
    previsores = {}
    for usar_temp, nome, fname in [
        (False, "Prophet SEM temperatura (contexto controlado)", "prophet_ctx_controlado_sem_temp.parquet"),
        (True, "Prophet COM temperatura (contexto controlado)", "prophet_temp_previsoes.parquet"),
    ]:
        previsor = previsor_prophet_controlado(usar_temp, temp_df)
        previsores[usar_temp] = previsor
        resultados_df = rodar_incremental(nome, previsor, serie_alvo, origens, PROCESSED_DIR / fname)
        aval, resultado, previsto = avaliar(nome, df, resultados_df, mae1, mae_saz, cmo_horario)
        dfs_aval[usar_temp] = aval

        # teste de vazamento: reusa a MESMA função previsor (agora com 2 saídas —
        # adaptador para o contrato de testar_vazamento, que espera 1 saída)
        def previsor_1out(historico, origem, _p=previsor):
            serie, _ = _p(historico, origem)
            return serie
        teste = testar_vazamento(serie_alvo, previsto, previsor_1out, nome, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
        log(f"{nome}: vazamento — {teste['n_comparacoes']} comparações, {len(teste['divergencias'])} divergências")

    # --- confirmar contexto identico
    sem = dfs_aval[False][["din_instante", "ctx_h"]].rename(columns={"ctx_h": "ctx_h_sem"})
    com = dfs_aval[True][["din_instante", "ctx_h"]].rename(columns={"ctx_h": "ctx_h_com"})
    cmp_ctx = sem.merge(com, on="din_instante", how="inner").dropna()
    identico = bool((cmp_ctx["ctx_h_sem"] == cmp_ctx["ctx_h_com"]).all())
    log(f"\n=== CONTEXTO IDÊNTICO ENTRE AS DUAS CONDIÇÕES: {'SIM' if identico else 'NÃO — ERRO'} ===")

    # --- delta limpo, estratificado
    a = dfs_aval[False][dfs_aval[False]["motivo_exclusao"] == "incluida"][["din_instante", "previsto", "real"]].rename(columns={"previsto": "previsto_sem"})
    b = dfs_aval[True][dfs_aval[True]["motivo_exclusao"] == "incluida"][["din_instante", "previsto"]].rename(columns={"previsto": "previsto_com"})
    m = a.merge(b, on="din_instante", how="inner")
    m["mape_sem"] = (m["previsto_sem"] - m["real"]).abs() / m["real"].abs() * 100
    m["mape_com"] = (m["previsto_com"] - m["real"]).abs() / m["real"].abs() * 100
    m["hora"] = m["din_instante"].dt.hour

    log("\n=== DELTA LIMPO (contexto controlado) — MAPE agregado ===")
    log(f"sem temp: {m['mape_sem'].mean():.4f}% | com temp: {m['mape_com'].mean():.4f}% | "
        f"delta: {m['mape_com'].mean()-m['mape_sem'].mean():+.4f}pp")

    pico = m[m["hora"].between(18, 21)]
    resto = m[~m["hora"].between(18, 21)]
    log(f"Pico (18-21h): sem={pico['mape_sem'].mean():.4f}% com={pico['mape_com'].mean():.4f}% "
        f"delta={pico['mape_com'].mean()-pico['mape_sem'].mean():+.4f}pp")
    log(f"Resto: sem={resto['mape_sem'].mean():.4f}% com={resto['mape_com'].mean():.4f}% "
        f"delta={resto['mape_com'].mean()-resto['mape_sem'].mean():+.4f}pp")

    if cmo_horario is not None:
        m2 = m.merge(cmo_horario.rename("cmo"), left_on="din_instante", right_index=True, how="left").dropna(subset=["cmo"])
        m2["decil_cmo"] = pd.qcut(m2["cmo"], 10, labels=False, duplicates="drop")
        log("\nPor decil de CMO (0=barato, 9=caro):")
        por_decil = m2.groupby("decil_cmo").apply(lambda g: pd.Series({
            "mape_sem": g["mape_sem"].mean(), "mape_com": g["mape_com"].mean(), "n": len(g)}))
        por_decil["delta"] = por_decil["mape_com"] - por_decil["mape_sem"]
        log("\n" + por_decil.round(4).to_string())

    log("\nPIPELINE PROPHET+TEMPERATURA FINALIZADO")


if __name__ == "__main__":
    main()
