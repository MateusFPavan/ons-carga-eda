"""Pipeline noturno, não-supervisionado: integra temperatura e reavalia Prophet,
Chronos-2 e SARIMAX COM temperatura vs. SEM (recorte 2024-01-20+). Roda as 5 fases
em UM único processo, tolerante a falha por fase (log + segue), determinismo forçado
em tudo. Ver reports/temperatura_progresso.log para acompanhar.

DECISÃO DOCUMENTADA (tomada aqui por necessidade, não escondida): temperatura só
existe a partir de 2024-01-20. Contextos nominais (Prophet=2 anos, SARIMA=60d,
Chronos=2048h) alcançam datas anteriores a isso para a maior parte do período de
avaliação — Prophet só teria contexto de 2 anos TOTALMENTE coberto por temperatura
a partir de 2026-01-19 (quase o fim da série). Em vez de pular a maioria das
origens, o contexto é TRUNCADO ao que há de temperatura disponível
(contexto_efetivo = min(contexto_nominal, horas desde 2024-01-20)), para TODAS as
origens desde 2024-01-20 — sem pular nenhuma. Cada previsão é marcada com
`contexto_efetivo_h` para quem for analisar depois poder filtrar/ponderar por isso.
Isso é uma adaptação forçada pela cobertura de dado, não uma escolha metodológica
livre — revisar de manhã.
"""
import os

for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "STAN_NUM_THREADS"):
    os.environ[var] = "1"

import json
import subprocess
import sys
import time
import traceback
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

RAIZ = Path(__file__).resolve().parent
SRC = RAIZ / "src"
sys.path.insert(0, str(SRC))

from gerar_features import calcular_dst_ativo, calcular_is_feriado  # noqa: E402
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, SanityCheckError, avaliar_modelo, calcular_custo,
    calcular_mae_insample_naive1, calcular_mae_insample_naive_sazonal,
    carregar_cmo_horario_se, checar_cobertura_cmo, gerar_origens,
    rodar_walkforward, testar_vazamento, valores_equivalentes, verificar_grade_regular,
)

PROCESSED_DIR = RAIZ / "data" / "processed"
RAW_TEMP_DIR = RAIZ / "data" / "raw" / "temperatura"
LOG_PATH = RAIZ / "reports" / "temperatura_progresso.log"
CIDADES = ["Sao_Paulo", "Rio_de_Janeiro", "Belo_Horizonte", "Brasilia", "Goiania"]
INICIO_TEMP = pd.Timestamp("2024-01-20")
FIM_AVALIACAO = pd.Timestamp("2026-07-15 23:00:00")
N_AMOSTRAS_VAZAMENTO = 30
SEED_VAZAMENTO = 42


def log(msg: str):
    linha = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(linha, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def commit(mensagem: str, arquivos: list):
    try:
        existentes = [a for a in arquivos if (RAIZ / a).exists()]
        if not existentes:
            log(f"COMMIT PULADO ('{mensagem}'): nenhum arquivo existente para adicionar.")
            return
        subprocess.run(["git", "add"] + existentes, cwd=RAIZ, check=True, capture_output=True)
        r = subprocess.run(["git", "commit", "-m", mensagem], cwd=RAIZ, capture_output=True, text=True)
        if r.returncode == 0:
            log(f"COMMIT OK: {mensagem}")
        else:
            log(f"COMMIT SEM MUDANÇAS ou falhou ({mensagem}): {r.stdout.strip()} {r.stderr.strip()}")
    except Exception as e:
        log(f"ERRO ao commitar '{mensagem}': {e}")


# ---------------------------------------------------------------------------
# FASE 1 — features de temperatura
# ---------------------------------------------------------------------------

def carregar_temperatura_cidade(cidade: str) -> pd.Series:
    frames = []
    for sufixo in ("2024_2025", "jan2026", "fev_jul2026"):
        fpath = RAW_TEMP_DIR / f"openmeteo_previous_day1_{cidade}_{sufixo}.json"
        if not fpath.exists():
            raise FileNotFoundError(str(fpath))
        j = json.loads(fpath.read_text(encoding="utf-8"))
        frames.append(pd.DataFrame({"ds": pd.to_datetime(j["hourly"]["time"]), "temp": j["hourly"]["temperature_2m_previous_day1"]}))
    df = pd.concat(frames, ignore_index=True).drop_duplicates("ds").sort_values("ds").reset_index(drop=True)
    return df.set_index("ds")["temp"]


def fase1_features_temperatura():
    log("FASE 1: iniciando integração de features de temperatura")
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    fim_serie = df["din_instante"].max()
    grade = pd.date_range(INICIO_TEMP, fim_serie, freq="h")

    saida = pd.DataFrame({"din_instante": grade})
    for cidade in CIDADES:
        serie_temp = carregar_temperatura_cidade(cidade)
        saida[f"temp_{cidade}"] = serie_temp.reindex(grade).to_numpy(dtype="float64")

    n_nan_total = int(saida[[f"temp_{c}" for c in CIDADES]].isna().sum().sum())
    log(f"FASE 1: {len(saida)} linhas ({INICIO_TEMP.date()} a {fim_serie.date()}), {n_nan_total} NaN totais nas 5 colunas")

    # checagem de vazamento: previous_day1 é por construção o valor previsto 24h
    # antes (fato documentado em FACTS.md seção G) — aqui só confirmamos que a
    # feature de D não usa nenhuma coluna/observação futura: o alinhamento é
    # 1:1 por din_instante, sem lookahead de índice.
    desalinhado = not saida["din_instante"].equals(pd.Series(grade))
    log(f"FASE 1: alinhamento por din_instante correto (sem deslocamento de índice): {'NÃO — ERRO' if desalinhado else 'OK'}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "features_temperatura.parquet"
    saida.to_parquet(out_path, index=False)
    log(f"FASE 1: salvo em {out_path}")
    log("FASE 1: CONCLUÍDA")
    commit("temperatura fase 1: features de temperatura", ["run_temperatura_pipeline.py", str(LOG_PATH.relative_to(RAIZ))])
    return saida.set_index("din_instante")


# ---------------------------------------------------------------------------
# util comum: contexto truncado à cobertura de temperatura
# ---------------------------------------------------------------------------

CONTEXTO_MINIMO_H = 720  # 30 dias — abaixo disso, ajuste com 6 exógenas (dst+5temp) não é confiável


def contexto_efetivo_horas(origem: pd.Timestamp, nominal_h: int) -> int:
    """Retorna None se não há contexto mínimo (30d) disponível ainda — o chamador
    deve pular a origem, não tentar ajustar com dado insuficiente (corrigido após
    a 1ª rodada: Prophet quebrou a fase inteira com contexto de 1h; SARIMAX gerou
    previsões explosivas com poucos dias de dado e 6 exógenas)."""
    disponivel_h = int((origem - INICIO_TEMP) / pd.Timedelta(hours=1))
    if disponivel_h < CONTEXTO_MINIMO_H:
        return None
    return min(nominal_h, disponivel_h)


LIMITE_PLAUSIVEL_MWH = 200_000  # bem acima do máximo histórico (~62.150) — além disso é explosão numérica, não previsão


def montar_cov_temp(temp_df: pd.DataFrame, idx: pd.DatetimeIndex, dst_fn=calcular_dst_ativo) -> dict:
    cov = {"dst_ativo": dst_fn(pd.Series(idx)).astype(float).to_numpy()}
    for cidade in CIDADES:
        cov[f"temp_{cidade}"] = temp_df[f"temp_{cidade}"].reindex(idx).to_numpy(dtype="float64")
    return cov


# ---------------------------------------------------------------------------
# FASE 2 — Prophet + temperatura
# ---------------------------------------------------------------------------

def fase2_prophet_temp(df, temp_df, origens, serie_alvo, mae1, mae_saz, cmo_horario):
    log("FASE 2: iniciando Prophet + temperatura (contexto nominal 2 anos, truncado por cobertura)")
    from prophet import Prophet
    NOMINAL_H = 17520

    cache = {}

    def previsor(historico, origem):
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        ctx_h = contexto_efetivo_horas(origem, NOMINAL_H)
        if ctx_h is None:
            log(f"FASE 2: origem {origem.date()} SEM contexto mínimo (<30d de temperatura) — NaN, pulando")
            return pd.Series(np.nan, index=horas_alvo)

        contexto = historico.iloc[-ctx_h:]

        try:
            train = pd.DataFrame({"ds": contexto.index, "y": contexto.values})
            train["dst_ativo"] = calcular_dst_ativo(train["ds"]).astype(float).values
            train["is_feriado"] = calcular_is_feriado(train["ds"]).astype(float).values
            for cidade in CIDADES:
                train[f"temp_{cidade}"] = temp_df[f"temp_{cidade}"].reindex(contexto.index).to_numpy(dtype="float64")

            m = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=True)
            m.add_regressor("dst_ativo")
            m.add_regressor("is_feriado")
            for cidade in CIDADES:
                m.add_regressor(f"temp_{cidade}")
            m.fit(train, seed=42)

            futuro = pd.DataFrame({"ds": horas_alvo})
            futuro["dst_ativo"] = calcular_dst_ativo(futuro["ds"]).astype(float).values
            futuro["is_feriado"] = calcular_is_feriado(futuro["ds"]).astype(float).values
            for cidade in CIDADES:
                futuro[f"temp_{cidade}"] = temp_df[f"temp_{cidade}"].reindex(horas_alvo).to_numpy(dtype="float64")

            amostras = m.predictive_samples(futuro)["yhat"]
            p05, p10, mediana, p90, p95 = np.percentile(amostras, [5, 10, 50, 90, 95], axis=1)
            cache[origem] = {"p05": p05, "p10": p10, "p90": p90, "p95": p95, "ctx_h": ctx_h}
            return pd.Series(mediana, index=horas_alvo)
        except Exception as e:
            log(f"FASE 2: origem {origem.date()} FALHOU ({e}) — NaN, pulando")
            return pd.Series(np.nan, index=horas_alvo)

    t0 = time.time()
    previsto = rodar_walkforward(serie_alvo, origens, previsor)
    tempo = time.time() - t0
    log(f"FASE 2: walk-forward concluído em {tempo/60:.1f} min ({len(origens)} origens)")

    saida = _finalizar_e_salvar(df, previsto, cache, mae1, mae_saz, cmo_horario,
                                 PROCESSED_DIR / "prophet_temp_previsoes.parquet", "FASE 2")

    log(f"FASE 2: testando vazamento ({N_AMOSTRAS_VAZAMENTO} origens)")
    teste = testar_vazamento(serie_alvo, previsto, previsor, "Prophet+temp", N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
    log(f"FASE 2: vazamento — {teste['n_comparacoes']} comparações, {len(teste['divergencias'])} divergências "
        f"(esperado 0 com determinismo forçado; Prophet pode ter não-determinismo residual do Stan — ver commit fb62833)")

    commit("temperatura fase 2: Prophet", ["run_temperatura_pipeline.py", str(LOG_PATH.relative_to(RAIZ))])
    log("FASE 2: CONCLUÍDA")
    return saida


# ---------------------------------------------------------------------------
# FASE 3 — Chronos-2 + covariáveis
# ---------------------------------------------------------------------------

def fase3_chronos_temp(df, temp_df, origens, serie_alvo, mae1, mae_saz, cmo_horario):
    log("FASE 3: iniciando Chronos-2 120M + covariáveis (contexto nominal 2048h, truncado por cobertura)")
    from chronos import BaseChronosPipeline
    NOMINAL_H = 2048
    pipeline = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map="cpu")

    cache = {}

    def previsor(historico, origem):
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        ctx_h = contexto_efetivo_horas(origem, NOMINAL_H)
        if ctx_h is None:
            log(f"FASE 3: origem {origem.date()} SEM contexto mínimo (<30d de temperatura) — NaN, pulando")
            return pd.Series(np.nan, index=horas_alvo)

        contexto_idx = historico.iloc[-ctx_h:].index
        target = historico.loc[contexto_idx].to_numpy(dtype="float32")

        try:
            past_cov = montar_cov_temp(temp_df, contexto_idx)
            future_cov = montar_cov_temp(temp_df, horas_alvo)
            past_cov = {k: v.astype("float32") for k, v in past_cov.items()}
            future_cov = {k: v.astype("float32") for k, v in future_cov.items()}

            quantis, _ = pipeline.predict_quantiles(
                inputs=[{"target": target, "past_covariates": past_cov, "future_covariates": future_cov}],
                prediction_length=24, quantile_levels=[0.05, 0.1, 0.5, 0.9, 0.95],
            )
        except Exception as e:
            log(f"FASE 3: origem {origem.date()} FALHOU ({e}) — NaN, pulando")
            return pd.Series(np.nan, index=horas_alvo)
        arr = np.asarray(quantis[0][0])
        cache[origem] = {"p05": arr[:, 0], "p10": arr[:, 1], "p90": arr[:, 3], "p95": arr[:, 4], "ctx_h": ctx_h}
        return pd.Series(arr[:, 2], index=horas_alvo)

    t0 = time.time()
    previsto = rodar_walkforward(serie_alvo, origens, previsor)
    tempo = time.time() - t0
    log(f"FASE 3: walk-forward concluído em {tempo/60:.1f} min ({len(origens)} origens)")

    saida = _finalizar_e_salvar(df, previsto, cache, mae1, mae_saz, cmo_horario,
                                 PROCESSED_DIR / "chronos_temp_previsoes.parquet", "FASE 3")

    log(f"FASE 3: testando vazamento ({N_AMOSTRAS_VAZAMENTO} origens)")
    teste = testar_vazamento(serie_alvo, previsto, previsor, "Chronos+temp", N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
    log(f"FASE 3: vazamento — {teste['n_comparacoes']} comparações, {len(teste['divergencias'])} divergências")

    commit("temperatura fase 3: Chronos-2", ["run_temperatura_pipeline.py", str(LOG_PATH.relative_to(RAIZ))])
    log("FASE 3: CONCLUÍDA")
    return saida


# ---------------------------------------------------------------------------
# FASE 4 — SARIMAX + temperatura (salva incrementalmente)
# ---------------------------------------------------------------------------

def fase4_sarimax_temp(df, temp_df, origens, serie_alvo, mae1, mae_saz, cmo_horario):
    log("FASE 4: iniciando SARIMAX + temperatura (contexto nominal 60d, truncado por cobertura)")
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    NOMINAL_H = 1440
    ORDEM, ORDEM_SAZ = (1, 1, 1), (1, 0, 1, 24)
    out_path = PROCESSED_DIR / "sarimax_temp_previsoes.parquet"

    linhas_salvas = []
    cache = {}
    t_inicio_fase = time.time()
    TETO_S = 3 * 3600

    for i, origem in enumerate(origens):
        if time.time() - t_inicio_fase > TETO_S:
            log(f"FASE 4: TETO DE 3h ATINGIDO em {i}/{len(origens)} origens — parando aqui, salvando o que tem.")
            break
        idx_corte = serie_alvo.index.searchsorted(origem)
        historico = serie_alvo.iloc[:idx_corte]
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        ctx_h = contexto_efetivo_horas(origem, NOMINAL_H)
        if ctx_h is None:
            log(f"FASE 4: origem {origem.date()} SEM contexto mínimo (<30d de temperatura) — pulando")
            for h in horas_alvo:
                linhas_salvas.append({"din_instante": h, "origem": origem, "previsto": np.nan,
                                       "p10": np.nan, "p90": np.nan, "p05": np.nan, "p95": np.nan,
                                       "convergiu": False, "ctx_h": 0, "erro_fit": "contexto insuficiente"})
            continue
        contexto = historico.iloc[-ctx_h:]
        y = contexto.to_numpy(dtype="float64")

        cov_hist = montar_cov_temp(temp_df, contexto.index)
        cov_fut = montar_cov_temp(temp_df, horas_alvo)
        exog_hist = np.column_stack([cov_hist[k] for k in sorted(cov_hist)])
        exog_fut = np.column_stack([cov_fut[k] for k in sorted(cov_fut)])

        try:
            modelo = SARIMAX(y, exog=exog_hist, order=ORDEM, seasonal_order=ORDEM_SAZ,
                              enforce_stationarity=False, enforce_invertibility=False)
            resultado = modelo.fit(disp=False)
            prev = resultado.get_forecast(steps=24, exog=exog_fut)
            media = np.asarray(prev.predicted_mean)
            ic80 = np.asarray(prev.conf_int(alpha=0.20))
            ic90 = np.asarray(prev.conf_int(alpha=0.10))
            convergiu = bool(resultado.mle_retvals.get("converged", False))
            # sanidade: descarta explosao numerica (coeficiente instavel passando
            # despercebido por enforce_stationarity=False) como nao-convergencia,
            # nao como previsao valida
            if np.any(np.abs(media) > LIMITE_PLAUSIVEL_MWH) or not np.all(np.isfinite(media)):
                convergiu = False
                media = np.full(24, np.nan)
                ic80 = np.full((24, 2), np.nan)
                ic90 = np.full((24, 2), np.nan)
            for j, h in enumerate(horas_alvo):
                linhas_salvas.append({"din_instante": h, "origem": origem, "previsto": media[j],
                                       "p10": ic80[j, 0], "p90": ic80[j, 1], "p05": ic90[j, 0], "p95": ic90[j, 1],
                                       "convergiu": convergiu, "ctx_h": ctx_h, "erro_fit": None})
        except Exception as e:
            log(f"FASE 4: origem {origem.date()} FALHOU ({e}) — pulando")
            for h in horas_alvo:
                linhas_salvas.append({"din_instante": h, "origem": origem, "previsto": np.nan,
                                       "p10": np.nan, "p90": np.nan, "p05": np.nan, "p95": np.nan,
                                       "convergiu": False, "ctx_h": ctx_h, "erro_fit": str(e)})

        if (i + 1) % 50 == 0 or i == len(origens) - 1:
            pd.DataFrame(linhas_salvas).to_parquet(out_path, index=False)
            log(f"FASE 4: progresso {i+1}/{len(origens)} origens, salvo incrementalmente em {out_path}")

    pd.DataFrame(linhas_salvas).to_parquet(out_path, index=False)
    saida = pd.DataFrame(linhas_salvas)
    n_convergiu = int(saida.groupby("origem")["convergiu"].first().sum())
    n_origens_processadas = saida["origem"].nunique()
    log(f"FASE 4: {n_origens_processadas} origens processadas, {n_convergiu} convergiram "
        f"({n_convergiu/n_origens_processadas*100:.1f}%)")

    valida = saida.dropna(subset=["previsto"])
    previsto_fmt = valida[["din_instante", "previsto"]].drop_duplicates("din_instante")
    if len(previsto_fmt):
        resultado_m = avaliar_modelo(df, previsto_fmt, mae1, mae_saz)
        custo = calcular_custo(resultado_m["avaliacao"], cmo_horario) if cmo_horario is not None else None
        log(f"FASE 4: MAPE={resultado_m['mape']:.4f}% MASE(sazonal)={resultado_m['mase_sazonal']:.4f} "
            f"custo={'R$ %.2f' % custo['custo_total'] if custo else 'N/D'} (sobre origens processadas)")

    commit("temperatura fase 4: SARIMAX", ["run_temperatura_pipeline.py", str(LOG_PATH.relative_to(RAIZ))])
    log("FASE 4: CONCLUÍDA (ou parcial, ver log acima)")
    return saida


# ---------------------------------------------------------------------------
# helper comum de avaliação + salvamento
# ---------------------------------------------------------------------------

def _finalizar_e_salvar(df, previsto, cache, mae1, mae_saz, cmo_horario, out_path, tag):
    resultado = avaliar_modelo(df, previsto, mae1, mae_saz)
    linhas = []
    for origem, d in cache.items():
        horas = pd.date_range(origem, periods=24, freq="h")
        for i, h in enumerate(horas):
            linhas.append({"din_instante": h, "p05": d["p05"][i], "p10": d["p10"][i],
                            "p90": d["p90"][i], "p95": d["p95"][i], "ctx_h": d["ctx_h"]})
    calib = pd.DataFrame(linhas)
    avaliacao = resultado["avaliacao"].merge(calib, on="din_instante", how="left")
    incluida = avaliacao[avaliacao["motivo_exclusao"] == "incluida"]
    cobertura_80 = float(((incluida["real"] >= incluida["p10"]) & (incluida["real"] <= incluida["p90"])).mean())
    cobertura_90 = float(((incluida["real"] >= incluida["p05"]) & (incluida["real"] <= incluida["p95"])).mean())
    custo = calcular_custo(resultado["avaliacao"], cmo_horario) if cmo_horario is not None else None

    log(f"{tag}: MAPE={resultado['mape']:.4f}% RMSE={resultado['rmse']:.2f} "
        f"MASE(1passo)={resultado['mase_naive1']:.4f} MASE(sazonal)={resultado['mase_sazonal']:.4f} "
        f"cobertura80={cobertura_80*100:.2f}% cobertura90={cobertura_90*100:.2f}% "
        f"custo={'R$ %.2f' % custo['custo_total'] if custo else 'N/D'}")

    avaliacao.to_parquet(out_path, index=False)
    log(f"{tag}: salvo em {out_path}")
    return avaliacao


# ---------------------------------------------------------------------------
# FASE 5 — consolidação
# ---------------------------------------------------------------------------

def fase5_consolidacao(df, cmo_horario):
    log("FASE 5: iniciando consolidação (só previsões já salvas, sem re-rodar)")
    arquivos_com_temp = {
        "Prophet+temp": PROCESSED_DIR / "prophet_temp_previsoes.parquet",
        "Chronos+temp": PROCESSED_DIR / "chronos_temp_previsoes.parquet",
        "SARIMAX+temp": PROCESSED_DIR / "sarimax_temp_previsoes.parquet",
    }
    arquivos_sem_temp = {
        "SARIMAX": PROCESSED_DIR / "sarima_previsoes_60d.parquet",
    }

    linhas_resumo = []
    for nome, fpath in {**arquivos_com_temp, **arquivos_sem_temp}.items():
        if not fpath.exists():
            log(f"FASE 5: {nome} — arquivo ausente ({fpath}), pulando dessa comparação")
            continue
        d = pd.read_parquet(fpath)
        if "din_instante" not in d.columns:
            continue
        d = d[d["din_instante"] >= INICIO_TEMP]
        if "motivo_exclusao" in d.columns:
            d = d[d["motivo_exclusao"] == "incluida"]
        else:
            d = d.dropna(subset=["previsto"])
        if "real" not in d.columns:
            real_serie = df.set_index("din_instante")["val_cargaenergiahomwmed"]
            d["real"] = d["din_instante"].map(real_serie)
        d = d.dropna(subset=["previsto", "real"])
        if len(d) == 0:
            continue
        erro = (d["previsto"] - d["real"]).abs()
        mape = float((erro / d["real"].abs()).mean() * 100)
        rmse = float(np.sqrt(((d["previsto"] - d["real"]) ** 2).mean()))
        linhas_resumo.append({"modelo": nome, "n_horas_2024_01_20+": len(d), "mape": mape, "rmse": rmse})
        log(f"FASE 5: {nome} (recorte 2024-01-20+): n={len(d)} MAPE={mape:.4f}% RMSE={rmse:.2f}")

    resumo = pd.DataFrame(linhas_resumo)
    out_path = PROCESSED_DIR / "temperatura_consolidacao.parquet"
    resumo.to_parquet(out_path, index=False)
    log(f"FASE 5: resumo consolidado salvo em {out_path}")
    log("FASE 5: CONCLUÍDA — comparação com/sem detalhada (deltas, estratificação por hora/CMO) fica para a consolidação manual, conforme pedido (\"a consolidação final vem depois, comigo\")")
    commit("temperatura fase 5: consolidacao", ["run_temperatura_pipeline.py", str(LOG_PATH.relative_to(RAIZ))])


# ---------------------------------------------------------------------------
def main():
    log("=" * 70)
    log("INÍCIO DO PIPELINE DE TEMPERATURA (não-supervisionado)")
    log("=" * 70)

    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()
    mae1, _ = calcular_mae_insample_naive1(df, INICIO_TEMP)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_TEMP, 168)
    origens = gerar_origens(df, INICIO_TEMP)
    log(f"Período de comparação com temperatura: {INICIO_TEMP.date()} a {df['din_instante'].max().date()} "
        f"({len(origens)} origens)")

    fim_serie = df["din_instante"].max()
    cobertura_cmo = checar_cobertura_cmo(INICIO_TEMP.year, fim_serie.year)
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"]) if cobertura_cmo["completo"] else None
    if cmo_horario is None:
        log(f"AVISO: CMO incompleto ({cobertura_cmo}) — métricas de custo ficarão N/D")

    temp_df = None
    try:
        temp_df = fase1_features_temperatura()
    except Exception as e:
        log(f"FASE 1 FALHOU: {e}\n{traceback.format_exc()}")
        log("Sem temp_df, fases 2-4 não podem rodar. Abortando pipeline.")
        return

    try:
        fase2_prophet_temp(df, temp_df, origens, serie_alvo, mae1, mae_saz, cmo_horario)
    except Exception as e:
        log(f"FASE 2 FALHOU: {e}\n{traceback.format_exc()}")

    try:
        fase3_chronos_temp(df, temp_df, origens, serie_alvo, mae1, mae_saz, cmo_horario)
    except Exception as e:
        log(f"FASE 3 FALHOU: {e}\n{traceback.format_exc()}")

    try:
        fase4_sarimax_temp(df, temp_df, origens, serie_alvo, mae1, mae_saz, cmo_horario)
    except Exception as e:
        log(f"FASE 4 FALHOU: {e}\n{traceback.format_exc()}")

    try:
        fase5_consolidacao(df, cmo_horario)
    except Exception as e:
        log(f"FASE 5 FALHOU: {e}\n{traceback.format_exc()}")

    log("=" * 70)
    log("PIPELINE FINALIZADO (ver acima quais fases completaram/falharam/pularam)")
    log("=" * 70)


if __name__ == "__main__":
    main()
