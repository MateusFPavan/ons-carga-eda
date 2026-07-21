"""Tarefa A: isola o efeito da temperatura do efeito do contexto truncado no
Chronos-2. Roda DUAS condições, idênticas em tudo (mesmas origens 2024-01-20+,
MESMO contexto efetivo truncado por origem — a mesma lógica de
run_temperatura_pipeline.py, incluindo o piso de 30 dias) — só muda se as 5
temperaturas entram como covariável. dst_ativo entra nas DUAS condições, porque
já entrava na condição com-temperatura do pipeline (isola só o efeito da
temperatura, não do dst_ativo).
"""
import os
for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[var] = "1"

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_features import calcular_dst_ativo  # noqa: E402
from modelo_naive import (  # noqa: E402
    CARGA_SE_PATH, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO, avaliar_modelo,
    calcular_custo, calcular_mae_insample_naive1, calcular_mae_insample_naive_sazonal,
    carregar_cmo_horario_se, checar_cobertura_cmo, gerar_origens, rodar_walkforward,
    testar_vazamento, verificar_grade_regular,
)

RAIZ = Path(__file__).resolve().parent.parent
RAW_TEMP_DIR = RAIZ / "data" / "raw" / "temperatura"
PROCESSED_DIR = RAIZ / "data" / "processed"
CIDADES = ["Sao_Paulo", "Rio_de_Janeiro", "Belo_Horizonte", "Brasilia", "Goiania"]
INICIO_TEMP = pd.Timestamp("2024-01-20")
NOMINAL_H = 2048
CONTEXTO_MINIMO_H = 720  # mesmo piso do pipeline (corrigido, commit 6ae9ecc)


def contexto_efetivo_horas(origem: pd.Timestamp) -> int:
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


def previsor_chronos_controlado(pipeline, usar_temperatura: bool, temp_df: pd.DataFrame, cache_ctx: dict):
    def prever(historico, origem):
        horas_alvo = pd.date_range(origem, periods=24, freq="h")
        ctx_h = contexto_efetivo_horas(origem)
        if ctx_h is None:
            cache_ctx[origem] = None
            return pd.Series(np.nan, index=horas_alvo)

        contexto_idx = historico.iloc[-ctx_h:].index
        target = historico.loc[contexto_idx].to_numpy(dtype="float32")

        past_cov = {"dst_ativo": calcular_dst_ativo(pd.Series(contexto_idx)).astype("float32").to_numpy()}
        future_cov = {"dst_ativo": calcular_dst_ativo(pd.Series(horas_alvo)).astype("float32").to_numpy()}
        if usar_temperatura:
            for cidade in CIDADES:
                past_cov[f"temp_{cidade}"] = temp_df[f"temp_{cidade}"].reindex(contexto_idx).to_numpy(dtype="float32")
                future_cov[f"temp_{cidade}"] = temp_df[f"temp_{cidade}"].reindex(horas_alvo).to_numpy(dtype="float32")

        quantis, _ = pipeline.predict_quantiles(
            inputs=[{"target": target, "past_covariates": past_cov, "future_covariates": future_cov}],
            prediction_length=24, quantile_levels=[0.05, 0.1, 0.5, 0.9, 0.95],
        )
        arr = np.asarray(quantis[0][0])
        cache_ctx[origem] = {"ctx_h": ctx_h, "p05": arr[:, 0], "p10": arr[:, 1], "p90": arr[:, 3], "p95": arr[:, 4]}
        return pd.Series(arr[:, 2], index=horas_alvo)
    return prever


def avaliar_e_estratificar(df, previsto, cache, mae1, mae_saz, cmo_horario, nome, out_path):
    resultado = avaliar_modelo(df, previsto, mae1, mae_saz)
    linhas = []
    for origem, d in cache.items():
        if d is None:
            continue
        horas = pd.date_range(origem, periods=24, freq="h")
        for i, h in enumerate(horas):
            linhas.append({"din_instante": h, "p05": d["p05"][i], "p10": d["p10"][i],
                            "p90": d["p90"][i], "p95": d["p95"][i], "ctx_h": d["ctx_h"]})
    calib = pd.DataFrame(linhas)
    avaliacao = resultado["avaliacao"].merge(calib, on="din_instante", how="left")
    incluida = avaliacao[avaliacao["motivo_exclusao"] == "incluida"].dropna(subset=["p10"])
    cobertura_80 = float(((incluida["real"] >= incluida["p10"]) & (incluida["real"] <= incluida["p90"])).mean())
    cobertura_90 = float(((incluida["real"] >= incluida["p05"]) & (incluida["real"] <= incluida["p95"])).mean())
    custo = calcular_custo(resultado["avaliacao"], cmo_horario) if cmo_horario is not None else None

    print(f"\n=== {nome} ===")
    print(f"MAPE={resultado['mape']:.4f}% RMSE={resultado['rmse']:.2f} "
          f"MASE(1passo)={resultado['mase_naive1']:.4f} MASE(sazonal)={resultado['mase_sazonal']:.4f}")
    print(f"Cobertura 80%={cobertura_80*100:.2f}% Cobertura 90%={cobertura_90*100:.2f}%")
    print(f"Custo total: R$ {custo['custo_total']:,.2f}" if custo else "Custo: N/D")
    print(f"Contexto efetivo — min={incluida['ctx_h'].min()} max={incluida['ctx_h'].max()} media={incluida['ctx_h'].mean():.1f}h")

    avaliacao.to_parquet(out_path, index=False)
    print(f"Salvo em {out_path}")
    return avaliacao, resultado


def main():
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)
    fim_serie = df["din_instante"].max()
    origens = gerar_origens(df, INICIO_TEMP)
    serie_alvo = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()
    print(f"Período: {INICIO_TEMP.date()} a {fim_serie.date()} — {len(origens)} origens")

    mae1, _ = calcular_mae_insample_naive1(df, INICIO_TEMP)
    mae_saz, _ = calcular_mae_insample_naive_sazonal(df, INICIO_TEMP, 168)
    cobertura_cmo = checar_cobertura_cmo(INICIO_TEMP.year, fim_serie.year)
    cmo_horario = carregar_cmo_horario_se(cobertura_cmo["anos_presentes"]) if cobertura_cmo["completo"] else None

    temp_df = pd.DataFrame({"din_instante": pd.date_range(INICIO_TEMP, fim_serie, freq="h")})
    for cidade in CIDADES:
        temp_df[f"temp_{cidade}"] = carregar_temperatura_cidade(cidade).reindex(temp_df["din_instante"]).to_numpy()
    temp_df = temp_df.set_index("din_instante")

    from chronos import BaseChronosPipeline
    pipeline = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map="cpu")

    resultados = {}
    for usar_temp, nome, fname in [
        (False, "Chronos SEM temperatura (contexto controlado, +dst_ativo)", "chronos_ctx_controlado_sem_temp.parquet"),
        (True, "Chronos COM temperatura (contexto controlado, +dst_ativo)", "chronos_ctx_controlado_com_temp.parquet"),
    ]:
        cache_ctx = {}
        previsor = previsor_chronos_controlado(pipeline, usar_temp, temp_df, cache_ctx)
        t0 = time.time()
        previsto = rodar_walkforward(serie_alvo, origens, previsor)
        print(f"\n{nome}: walk-forward em {time.time()-t0:.1f}s")

        aval, resultado = avaliar_e_estratificar(df, previsto, cache_ctx, mae1, mae_saz, cmo_horario, nome,
                                                   PROCESSED_DIR / fname)
        resultados[usar_temp] = aval

        teste = testar_vazamento(serie_alvo, previsto, previsor, nome, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)
        print(f"Vazamento: {teste['n_comparacoes']} comparações, {len(teste['divergencias'])} divergências")

    # --- confirmar contexto identico entre as duas condicoes
    sem = resultados[False][["din_instante", "ctx_h"]].rename(columns={"ctx_h": "ctx_h_sem"})
    com = resultados[True][["din_instante", "ctx_h"]].rename(columns={"ctx_h": "ctx_h_com"})
    cmp_ctx = sem.merge(com, on="din_instante", how="inner").dropna()
    identico = bool((cmp_ctx["ctx_h_sem"] == cmp_ctx["ctx_h_com"]).all())
    print(f"\n=== CONTEXTO IDÊNTICO ENTRE AS DUAS CONDIÇÕES: {'SIM' if identico else 'NÃO — ERRO'} ===")

    # --- delta limpo (temperatura isolada), estratificado
    a = resultados[False][resultados[False]["motivo_exclusao"] == "incluida"][["din_instante", "previsto", "real"]].rename(columns={"previsto": "previsto_sem"})
    b = resultados[True][resultados[True]["motivo_exclusao"] == "incluida"][["din_instante", "previsto"]].rename(columns={"previsto": "previsto_com"})
    m = a.merge(b, on="din_instante", how="inner")
    m["mape_sem"] = (m["previsto_sem"] - m["real"]).abs() / m["real"].abs() * 100
    m["mape_com"] = (m["previsto_com"] - m["real"]).abs() / m["real"].abs() * 100
    m["hora"] = m["din_instante"].dt.hour

    print(f"\n=== DELTA LIMPO (contexto controlado) — MAPE agregado ===")
    print(f"sem temp: {m['mape_sem'].mean():.4f}% | com temp: {m['mape_com'].mean():.4f}% | "
          f"delta: {m['mape_com'].mean()-m['mape_sem'].mean():+.4f}pp")

    pico = m[m["hora"].between(18, 21)]
    resto = m[~m["hora"].between(18, 21)]
    print(f"\nPico (18-21h): sem={pico['mape_sem'].mean():.4f}% com={pico['mape_com'].mean():.4f}% "
          f"delta={pico['mape_com'].mean()-pico['mape_sem'].mean():+.4f}pp")
    print(f"Resto: sem={resto['mape_sem'].mean():.4f}% com={resto['mape_com'].mean():.4f}% "
          f"delta={resto['mape_com'].mean()-resto['mape_sem'].mean():+.4f}pp")

    if cmo_horario is not None:
        cmo_h = cmo_horario.rename("cmo")
        m2 = m.merge(cmo_h, left_on="din_instante", right_index=True, how="left").dropna(subset=["cmo"])
        m2["decil_cmo"] = pd.qcut(m2["cmo"], 10, labels=False, duplicates="drop")
        print("\nPor decil de CMO (0=barato, 9=caro):")
        por_decil = m2.groupby("decil_cmo").apply(lambda g: pd.Series({
            "mape_sem": g["mape_sem"].mean(), "mape_com": g["mape_com"].mean(), "n": len(g)}))
        por_decil["delta"] = por_decil["mape_com"] - por_decil["mape_sem"]
        print(por_decil.round(4).to_string())

    print("\n=== COMPARAÇÃO COM O DELTA DO PIPELINE NÃO-CONTROLADO ===")
    print("Pipeline (contexto NÃO controlado): sem=1.8150% com=1.7282% delta=-0.0868pp")
    print(f"Contexto controlado: sem={m['mape_sem'].mean():.4f}% com={m['mape_com'].mean():.4f}% "
          f"delta={m['mape_com'].mean()-m['mape_sem'].mean():+.4f}pp")


if __name__ == "__main__":
    main()
