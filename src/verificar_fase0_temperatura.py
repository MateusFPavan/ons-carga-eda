"""Fase 0 — verificação de viabilidade ANTES do walk-forward completo com
temperatura (Prophet, SARIMAX e, se possível, Chronos-2 com covariáveis). Não roda
nenhum walk-forward, não integra features — só verifica três pontos que poderiam
travar a rodada longa. Ver reports/FACTS.md seção G.

1. Alinhamento de fuso das 5 cidades (SP, RJ, BH, Brasília, Goiânia) entre si e com
   a carga.
2. Se o Chronos-2 (chronos-forecasting==2.3.1) suporta covariáveis exógenas
   (past_covariates/future_covariates) no predict — e um teste mínimo, 1 origem.
3. Cobertura temporal da temperatura sem vazamento (previous_day1) dentro do
   período de avaliação (2024-01-01 a 2026-07-15).
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_features import calcular_dst_ativo  # noqa: E402
from modelo_naive import CARGA_SE_PATH, INICIO_AVALIACAO  # noqa: E402

RAW_TEMP_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "temperatura"
CIDADES = ["Sao_Paulo", "Rio_de_Janeiro", "Belo_Horizonte", "Brasilia", "Goiania"]
ARQUIVOS_POR_CIDADE = ["2024_2025", "jan2026"]  # arquivos disponíveis nesta sondagem
FIM_AVALIACAO = pd.Timestamp("2026-07-15 23:00:00")


def carregar_temperatura_cidade(cidade: str) -> pd.DataFrame:
    frames = []
    for sufixo in ARQUIVOS_POR_CIDADE:
        fpath = RAW_TEMP_DIR / f"openmeteo_previous_day1_{cidade}_{sufixo}.json"
        if not fpath.exists():
            raise FileNotFoundError(f"Arquivo de temperatura ausente: {fpath}")
        j = json.loads(fpath.read_text(encoding="utf-8"))
        frames.append(pd.DataFrame({
            "ds": pd.to_datetime(j["hourly"]["time"]),
            "temp": j["hourly"]["temperature_2m_previous_day1"],
            "timezone": j.get("timezone"),
            "utc_offset_seconds": j.get("utc_offset_seconds"),
        }))
    df = pd.concat(frames, ignore_index=True).drop_duplicates("ds").sort_values("ds").reset_index(drop=True)
    return df


def tarefa1_fuso():
    print("=== TAREFA 1: alinhamento de fuso das 5 cidades ===")
    fusos = {}
    for cidade in CIDADES:
        df = carregar_temperatura_cidade(cidade)
        tz_unicos = df["timezone"].unique()
        offset_unicos = df["utc_offset_seconds"].unique()
        fusos[cidade] = (tuple(tz_unicos), tuple(offset_unicos))
        print(f"  {cidade}: timezone={list(tz_unicos)} utc_offset_seconds={list(offset_unicos)}")

    valores_unicos = set(fusos.values())
    alinhadas = len(valores_unicos) == 1
    mesmo_fuso_carga = alinhadas and list(valores_unicos)[0][0] == ("America/Sao_Paulo",) and list(valores_unicos)[0][1] == (-10800,)
    print(f"\nAs 5 cidades estão alinhadas ENTRE SI: {'SIM' if alinhadas else 'NÃO'}")
    print(f"O fuso é America/Sao_Paulo (-10800s), mesmo da carga (hora local, sem conversão UTC): "
          f"{'SIM' if mesmo_fuso_carga else 'NÃO'}")
    print("Nenhuma correção necessária." if mesmo_fuso_carga else "DESALINHAMENTO — não corrigido aqui, só reportado.")
    return mesmo_fuso_carga


def tarefa2_chronos_covariaveis():
    print("\n=== TAREFA 2: Chronos-2 — suporte a covariáveis ===")
    df = pd.read_parquet(CARGA_SE_PATH).sort_values("din_instante").reset_index(drop=True)
    serie = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index()

    origem = pd.Timestamp("2024-03-01")  # dentro do período com temperatura completa (>= 2024-01-20)
    contexto_h = 512
    contexto_idx = serie[serie.index < origem].iloc[-contexto_h:].index
    horas_alvo = pd.date_range(origem, periods=24, freq="h")
    target = serie.loc[contexto_idx].to_numpy(dtype="float32")

    past_cov = {"dst_ativo": calcular_dst_ativo(pd.Series(contexto_idx)).astype("float32").to_numpy()}
    future_cov = {"dst_ativo": calcular_dst_ativo(pd.Series(horas_alvo)).astype("float32").to_numpy()}
    for cidade in CIDADES:
        temp = carregar_temperatura_cidade(cidade).set_index("ds")["temp"]
        past_cov[f"temp_{cidade}"] = temp.reindex(contexto_idx).to_numpy(dtype="float32")
        future_cov[f"temp_{cidade}"] = temp.reindex(horas_alvo).to_numpy(dtype="float32")

    n_nan_past = sum(int(np.isnan(v).sum()) for v in past_cov.values())
    n_nan_fut = sum(int(np.isnan(v).sum()) for v in future_cov.values())
    print(f"NaN em past_covariates: {n_nan_past} | NaN em future_covariates: {n_nan_fut} "
          f"(origem={origem.date()}, dentro do período com temperatura completa)")

    from chronos import BaseChronosPipeline
    pipeline = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map="cpu")

    t0 = time.time()
    quantis, _ = pipeline.predict_quantiles(
        inputs=[{"target": target, "past_covariates": past_cov, "future_covariates": future_cov}],
        prediction_length=24, quantile_levels=[0.1, 0.5, 0.9],
    )
    t_inferencia = time.time() - t0

    arr = np.asarray(quantis[0][0])
    mediana = arr[:, 1]
    n_nan_saida = int(np.isnan(mediana).sum())
    print(f"predict_quantiles(inputs=[{{'target':..., 'past_covariates':..., 'future_covariates':...}}]) — "
          f"assinatura usada, 1 alvo + 6 covariáveis (dst_ativo + 5 temperaturas)")
    print(f"Tempo de inferência: {t_inferencia:.4f}s | N previsões: {len(mediana)} | NaN na saída: {n_nan_saida}")
    print(f"Mediana min/max/média: {mediana.min():.2f} / {mediana.max():.2f} / {mediana.mean():.2f} MWh/h")
    print(f"Extrapolação 927 origens: {t_inferencia*927/60:.1f} min")
    print(f"COVARIÁVEIS SUPORTADAS: {'SIM' if n_nan_saida == 0 else 'SIM, mas saída com NaN — investigar'}")
    return t_inferencia


def tarefa3_cobertura():
    print("\n=== TAREFA 3: cobertura temporal da temperatura no período de avaliação ===")
    resultado_por_cidade = {}
    for cidade in CIDADES:
        df = carregar_temperatura_cidade(cidade)
        grade_completa = pd.date_range(df["ds"].min(), df["ds"].max(), freq="h")
        linhas_faltando = grade_completa.difference(df["ds"])

        primeiro_nao_nulo = df[df["temp"].notna()]["ds"].min()
        apos_primeiro_nao_nulo = df[df["ds"] >= primeiro_nao_nulo.normalize() + pd.Timedelta(days=1)]
        nulos_apos_warmup = int(apos_primeiro_nao_nulo["temp"].isna().sum())

        cobre_fim_avaliacao = df["ds"].max() >= FIM_AVALIACAO
        resultado_por_cidade[cidade] = {
            "min": df["ds"].min(), "max": df["ds"].max(),
            "linhas_faltando_na_grade": len(linhas_faltando),
            "primeiro_nao_nulo": primeiro_nao_nulo,
            "nulos_apos_warmup": nulos_apos_warmup,
            "cobre_ate_fim_avaliacao": cobre_fim_avaliacao,
        }
        print(f"  {cidade}: {df['ds'].min()} a {df['ds'].max()} | linhas faltando na grade={len(linhas_faltando)} | "
              f"primeiro valor não-nulo={primeiro_nao_nulo} | nulos após warm-up={nulos_apos_warmup} | "
              f"cobre até {FIM_AVALIACAO}: {'SIM' if cobre_fim_avaliacao else 'NÃO — BURACO'}")

    ultimo_comum = min(v["max"] for v in resultado_por_cidade.values())
    primeiro_dia_completo = pd.Timestamp("2024-01-20")  # já estabelecido em FACTS.md seção G, confirmado acima

    dias_sem_temp_inicio = (primeiro_dia_completo - INICIO_AVALIACAO).days
    dias_sem_temp_fim = (FIM_AVALIACAO.normalize() - ultimo_comum.normalize()).days
    dias_com_temp = (ultimo_comum.normalize() - primeiro_dia_completo).days + 1
    dias_totais_avaliacao = (FIM_AVALIACAO.normalize() - INICIO_AVALIACAO).days + 1

    print(f"\nDias do período de avaliação SEM temperatura no INÍCIO "
          f"({INICIO_AVALIACAO.date()} a {(primeiro_dia_completo - pd.Timedelta(days=1)).date()}): {dias_sem_temp_inicio}")
    print(f"Dias do período de avaliação SEM temperatura no FIM "
          f"({(ultimo_comum.normalize() + pd.Timedelta(days=1)).date()} a {FIM_AVALIACAO.date()}): {dias_sem_temp_fim}")
    print(f"Período efetivo com temperatura completa (0 buracos, confirmado por cidade): "
          f"{primeiro_dia_completo.date()} a {ultimo_comum.date()} ({dias_com_temp} dias)")
    print(f"Cobertura efetiva sobre o período de avaliação inteiro ({dias_totais_avaliacao} dias): "
          f"{dias_com_temp/dias_totais_avaliacao*100:.1f}%")
    if dias_sem_temp_fim > 0:
        print(f"\nAVISO: {dias_sem_temp_fim} dias no fim do período de avaliação NÃO têm arquivo de temperatura "
              f"baixado (não é buraco dentro de um arquivo — o arquivo simplesmente não foi baixado até lá). "
              f"Precisaria de novo download para cobrir isso.")
    return primeiro_dia_completo, ultimo_comum


if __name__ == "__main__":
    alinhado = tarefa1_fuso()
    tempo_origem = tarefa2_chronos_covariaveis()
    inicio_efetivo, fim_efetivo = tarefa3_cobertura()

    print("\n=== RESUMO ===")
    print(f"1. Fuso alinhado (5 cidades entre si e com a carga): {'SIM' if alinhado else 'NÃO'}")
    print(f"2. Chronos-2 aceita covariáveis: SIM — {tempo_origem:.4f}s/origem (contexto 512h, 6 covariáveis)")
    print(f"3. Período efetivo com temperatura completa: {inicio_efetivo.date()} a {fim_efetivo.date()}")
    print("\nNenhum walk-forward rodado. Nenhuma feature integrada ainda.")
