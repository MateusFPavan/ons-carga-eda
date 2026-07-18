"""Gera data/processed/features_se.parquet — features do modelo principal (SE/CO).

Execução de decisões já tomadas (reports/FACTS.md seção H, reports/ESCOPO.md). Não é
sondagem: não normaliza, não escalona, não usa estatística global da série. Toda
feature é computável no instante da previsão (day-ahead, corte às 00:00 do dia D —
informação disponível vai só até o fim do dia D-1). Se um sanity check ou o teste de
vazamento falhar, o script ABORTA (raise) — não conserta nada.
"""
import calendar
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays
import numpy as np
import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
CARGA_SE_PATH = PROCESSED_DIR / "carga_se.parquet"
OUT_PATH = PROCESSED_DIR / "features_se.parquet"
TZ = ZoneInfo("America/Sao_Paulo")

N_AMOSTRAS_VAZAMENTO = 30
SEED_VAZAMENTO = 42

# Janelas usadas pelos lags e médias móveis — única fonte de verdade, usada tanto
# no cálculo real (calcular_lags, calcular_medias_moveis) quanto na fórmula
# independente de NaN esperado (calcular_nan_esperado_*). Se alguém mudar uma
# janela aqui, o NaN esperado muda junto — não pode divergir em silêncio.
LAGS_HORAS = [24, 48, 168, 336]
JANELA_DIAS_MEDIA_168H = 7
JANELA_DIAS_MESMA_HORA_7D = 7


class SanityCheckError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Pré-condição: grade horária completa e regular (24 linhas/dia, sem duplicata).
# calcular_lags e calcular_medias_moveis reamostram por tempo (asfreq/calendário
# completo), então funcionam mesmo com lacunas — mas a ENTRADA real do projeto é
# conhecida (FACTS.md seção C) como regular, e um desvio aqui é sinal de regressão
# upstream, não algo para tratar em silêncio.
# ---------------------------------------------------------------------------

def verificar_grade_regular(df: pd.DataFrame) -> None:
    if not df["din_instante"].is_monotonic_increasing:
        raise SanityCheckError("din_instante não está ordenado.")
    if df["din_instante"].duplicated().any():
        raise SanityCheckError("din_instante tem timestamps duplicados.")
    dia = df["din_instante"].dt.date
    contagem = dia.value_counts()
    calendario_completo = pd.date_range(df["din_instante"].min().normalize(), df["din_instante"].max().normalize(), freq="D").date
    contagem = contagem.reindex(calendario_completo, fill_value=0)
    irregulares = contagem[contagem != 24]
    if len(irregulares) > 0:
        raise SanityCheckError(f"{len(irregulares)} dia(s) com != 24 registros: {irregulares.to_dict()}")


# ---------------------------------------------------------------------------
# 1. Calendário — função pura do timestamp, sem nenhuma consulta a dado histórico
# ---------------------------------------------------------------------------

def calcular_features_calendario(df: pd.DataFrame) -> pd.DataFrame:
    dt = df["din_instante"]
    hora = dt.dt.hour
    dia_semana = dt.dt.dayofweek
    mes = dt.dt.month
    dia_ano = dt.dt.dayofyear
    is_fim_de_semana = dia_semana >= 5

    dias_no_ano = dt.dt.year.apply(lambda a: 366 if calendar.isleap(a) else 365)

    return pd.DataFrame({
        "hora": hora.astype("int64"),
        "dia_semana": dia_semana.astype("int64"),
        "mes": mes.astype("int64"),
        "dia_ano": dia_ano.astype("int64"),
        "is_fim_de_semana": is_fim_de_semana.astype(bool),
        "hora_sin": np.sin(2 * np.pi * hora / 24),
        "hora_cos": np.cos(2 * np.pi * hora / 24),
        "dia_semana_sin": np.sin(2 * np.pi * dia_semana / 7),
        "dia_semana_cos": np.cos(2 * np.pi * dia_semana / 7),
        "dia_ano_sin": np.sin(2 * np.pi * dia_ano / dias_no_ano),
        "dia_ano_cos": np.cos(2 * np.pi * dia_ano / dias_no_ano),
    }, index=df.index)


# ---------------------------------------------------------------------------
# 2. Regime — dst_ativo via zoneinfo/IANA (não hardcoded); is_dst_transition
# propagado do parquet de entrada (já gerado por src/gerar_facts.py)
# ---------------------------------------------------------------------------

def calcular_dst_ativo(timestamps: pd.Series) -> pd.Series:
    """True se o relógio local (America/Sao_Paulo) está em horário de verão nesse
    instante. Usa zoneinfo/IANA — mesma fonte de verdade que src/gerar_facts.py
    seção D. fold=0 (interpretação padrão) nos 9 timestamps ambíguos/inexistentes;
    esses já são sinalizados separadamente por is_dst_transition."""
    def ativo(ts) -> bool:
        ts = pd.Timestamp(ts)
        dt_local = datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, tzinfo=TZ, fold=0)
        offset_dst = dt_local.dst()
        return offset_dst is not None and offset_dst != timedelta(0)

    return pd.Series([ativo(t) for t in timestamps], index=timestamps.index, dtype=bool)


# ---------------------------------------------------------------------------
# 5. Feriados nacionais brasileiros — biblioteca `holidays`, sem subdiv (só
# feriados nacionais, nenhum estadual/municipal)
# ---------------------------------------------------------------------------

def calcular_is_feriado(timestamps: pd.Series) -> pd.Series:
    anos = sorted(int(a) for a in pd.to_datetime(timestamps).dt.year.unique())
    feriados_br = holidays.Brazil(years=anos)
    datas = pd.to_datetime(timestamps).dt.date
    return pd.Series(datas.isin(feriados_br), index=timestamps.index, dtype=bool)


# ---------------------------------------------------------------------------
# 3. Lags de carga (todos >= 24h) — deslocamento por TEMPO (asfreq), não por
# posição de linha, para funcionar corretamente mesmo sobre um recorte com
# lacunas (usado pelo teste de vazamento)
# ---------------------------------------------------------------------------

def calcular_lags(df: pd.DataFrame) -> pd.DataFrame:
    serie = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index().asfreq("h")
    saida = pd.DataFrame({
        f"lag_{h}h": serie.shift(h) for h in LAGS_HORAS
    })
    return saida.reindex(df["din_instante"].values).set_axis(df.index)


# ---------------------------------------------------------------------------
# 4. Médias móveis — corte em 00:00 do dia D: o valor é o MESMO para todas as 24
# horas do dia D (a previsão day-ahead é feita de uma vez, no início do dia).
# Reamostrado para o calendário diário completo antes do shift/rolling, para
# funcionar corretamente sobre um recorte truncado (teste de vazamento).
# ---------------------------------------------------------------------------

def calcular_medias_moveis(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df[["din_instante", "val_cargaenergiahomwmed"]].copy()
    tmp["data"] = tmp["din_instante"].dt.date
    tmp["hora"] = tmp["din_instante"].dt.hour

    pivot = tmp.pivot(index="data", columns="hora", values="val_cargaenergiahomwmed")
    calendario_completo = pd.date_range(pivot.index.min(), pivot.index.max(), freq="D").date
    pivot = pivot.reindex(index=calendario_completo, columns=range(24))

    daily_mean = pivot.mean(axis=1, skipna=True)
    media_24h_por_dia = daily_mean.shift(1)
    media_168h_por_dia = daily_mean.shift(1).rolling(window=JANELA_DIAS_MEDIA_168H, min_periods=JANELA_DIAS_MEDIA_168H).mean()
    media_mesma_hora_pivot = pivot.shift(1).rolling(window=JANELA_DIAS_MESMA_HORA_7D, min_periods=JANELA_DIAS_MESMA_HORA_7D).mean()

    media_24h = tmp["data"].map(media_24h_por_dia)
    media_168h = tmp["data"].map(media_168h_por_dia)
    media_mesma_hora_7d = [media_mesma_hora_pivot.at[d, h] for d, h in zip(tmp["data"], tmp["hora"])]

    return pd.DataFrame({
        "media_24h": media_24h.values,
        "media_168h": media_168h.values,
        "media_mesma_hora_7d": media_mesma_hora_7d,
    }, index=df.index)


# ---------------------------------------------------------------------------
# Gate de NaN esperado — para cada lag/média móvel, deriva o conjunto de
# timestamps que DEVEM ficar NaN a partir de (janela + NaN brutos propagados),
# usando uma via de cálculo independente de calcular_lags/calcular_medias_moveis
# (aritmética de datas sobre os NaN brutos, não shift/rolling do pandas). Se a
# saída real divergir do esperado, ABORTA — pega regressão silenciosa se alguém
# mudar uma janela ou um min_periods sem perceber o efeito no NaN.
# ---------------------------------------------------------------------------

def _dias_totalmente_nan(df: pd.DataFrame) -> list:
    tmp = df[["din_instante", "val_cargaenergiahomwmed"]].copy()
    tmp["data"] = tmp["din_instante"].dt.date
    por_dia = tmp.groupby("data")["val_cargaenergiahomwmed"]
    nan_por_dia = por_dia.apply(lambda s: int(s.isna().sum()))
    total_por_dia = por_dia.size()
    return sorted(d for d in nan_por_dia.index if nan_por_dia[d] == total_por_dia[d])


def calcular_nan_esperado_lag(df: pd.DataFrame, lag_horas: int) -> set:
    """NaN esperado em lag_Nh = (1) as primeiras N horas da série (sem histórico
    suficiente) UNIÃO (2) para cada timestamp com valor bruto NaN em T0, o alvo
    T0+N horas (se existir na série) — o lag desse alvo aponta de volta para T0."""
    serie = df.set_index("din_instante")["val_cargaenergiahomwmed"].sort_index().asfreq("h")
    fim = serie.index[-1]

    esperado = set(serie.index[:lag_horas])
    raw_nan_ts = serie.index[serie.isna()]
    for t0 in raw_nan_ts:
        alvo = t0 + pd.Timedelta(hours=lag_horas)
        if alvo <= fim:
            esperado.add(alvo)
    return esperado


def calcular_nan_esperado_media_24h(df: pd.DataFrame) -> set:
    """NaN esperado em media_24h = dias sem D-1 (primeiro dia da série) UNIÃO dias
    cujo D-1 está inteiramente vazio (24 valores brutos NaN nesse D-1)."""
    dias = sorted(df["din_instante"].dt.date.unique())
    dias_validos = set(dias)
    dias_esperados = {dias[0]}
    for d0 in _dias_totalmente_nan(df):
        candidato = d0 + timedelta(days=1)
        if candidato in dias_validos:
            dias_esperados.add(candidato)
    return dias_esperados


def calcular_nan_esperado_media_168h(df: pd.DataFrame) -> set:
    """NaN esperado em media_168h = primeiros JANELA_DIAS_MEDIA_168H dias da série
    (sem histórico suficiente) UNIÃO, para cada dia totalmente vazio D0, os
    JANELA_DIAS_MEDIA_168H dias seguintes (a janela de 7 dias que os sucede inclui
    D0, que tem média diária NaN, então min_periods=7 derruba a janela inteira)."""
    dias = sorted(df["din_instante"].dt.date.unique())
    dias_validos = set(dias)
    dias_esperados = set(dias[:JANELA_DIAS_MEDIA_168H])
    for d0 in _dias_totalmente_nan(df):
        for k in range(1, JANELA_DIAS_MEDIA_168H + 1):
            candidato = d0 + timedelta(days=k)
            if candidato in dias_validos:
                dias_esperados.add(candidato)
    return dias_esperados


def calcular_nan_esperado_mesma_hora_7d(df: pd.DataFrame) -> set:
    """NaN esperado em media_mesma_hora_7d, por par (dia, hora) = primeiros
    JANELA_DIAS_MESMA_HORA_7D dias × todas as 24 horas (sem histórico) UNIÃO, para
    cada (T0=dia D0/hora h0) com valor bruto NaN, os pares (D0+k, h0) para
    k=1..JANELA_DIAS_MESMA_HORA_7D (a mesma hora h0, nos 7 dias seguintes, perde 1
    das 7 amostras por causa de T0 — min_periods derruba a janela inteira)."""
    tmp = df[["din_instante", "val_cargaenergiahomwmed"]].copy()
    tmp["data"] = tmp["din_instante"].dt.date
    tmp["hora"] = tmp["din_instante"].dt.hour

    dias = sorted(tmp["data"].unique())
    dias_validos = set(dias)
    primeiros = set(dias[:JANELA_DIAS_MESMA_HORA_7D])

    pares_esperados = {(d, h) for d in primeiros for h in range(24)}
    brutos_nan = tmp[tmp["val_cargaenergiahomwmed"].isna()]
    for d0, h0 in zip(brutos_nan["data"], brutos_nan["hora"]):
        for k in range(1, JANELA_DIAS_MESMA_HORA_7D + 1):
            candidato = d0 + timedelta(days=k)
            if candidato in dias_validos:
                pares_esperados.add((candidato, h0))
    return pares_esperados


def verificar_nan_esperado(df: pd.DataFrame, features: pd.DataFrame) -> None:
    erros = []

    for lag_horas in LAGS_HORAS:
        col = f"lag_{lag_horas}h"
        esperado = calcular_nan_esperado_lag(df, lag_horas)
        observado = set(features.loc[features[col].isna(), "din_instante"])
        if esperado != observado:
            faltando = sorted(str(t) for t in (esperado - observado))[:5]
            sobrando = sorted(str(t) for t in (observado - esperado))[:5]
            erros.append(f"{col}: NaN observado != esperado. faltando={faltando} sobrando={sobrando}")

    esperado_24h = calcular_nan_esperado_media_24h(df)
    observado_24h = set(features.loc[features["media_24h"].isna(), "din_instante"].dt.date)
    if esperado_24h != observado_24h:
        erros.append(
            f"media_24h: dias NaN observados != esperado. "
            f"faltando={sorted(esperado_24h - observado_24h)[:5]} sobrando={sorted(observado_24h - esperado_24h)[:5]}"
        )

    esperado_168h = calcular_nan_esperado_media_168h(df)
    observado_168h = set(features.loc[features["media_168h"].isna(), "din_instante"].dt.date)
    if esperado_168h != observado_168h:
        erros.append(
            f"media_168h: dias NaN observados != esperado. "
            f"faltando={sorted(esperado_168h - observado_168h)[:5]} sobrando={sorted(observado_168h - esperado_168h)[:5]}"
        )

    esperado_mesma_hora = calcular_nan_esperado_mesma_hora_7d(df)
    obs_mh = features.loc[features["media_mesma_hora_7d"].isna(), "din_instante"]
    observado_mesma_hora = set(zip(obs_mh.dt.date, obs_mh.dt.hour))
    if esperado_mesma_hora != observado_mesma_hora:
        erros.append(
            f"media_mesma_hora_7d: pares (dia,hora) NaN observados != esperado. "
            f"faltando={sorted(esperado_mesma_hora - observado_mesma_hora)[:5]} "
            f"sobrando={sorted(observado_mesma_hora - esperado_mesma_hora)[:5]}"
        )

    if erros:
        raise SanityCheckError("NaN observado diverge do NaN esperado (janela + NaN bruto propagado):\n" + "\n".join(erros))


# ---------------------------------------------------------------------------
# Teste de vazamento
# ---------------------------------------------------------------------------

def valores_equivalentes(a, b, rtol=1e-9, atol=1e-6) -> bool:
    a_nan = a is None or pd.isna(a)
    b_nan = b is None or pd.isna(b)
    if a_nan or b_nan:
        return bool(a_nan) == bool(b_nan)
    if isinstance(a, (bool, np.bool_)) or isinstance(b, (bool, np.bool_)):
        return bool(a) == bool(b)
    try:
        return math.isclose(float(a), float(b), rel_tol=rtol, abs_tol=atol)
    except (TypeError, ValueError):
        return a == b


def testar_vazamento(df: pd.DataFrame, features: pd.DataFrame, n_amostras: int, seed: int) -> dict:
    """Para N timestamps aleatórios (seed fixa), prova que cada feature não usa
    informação do dia D:
    - calendário/dst_ativo/is_feriado: recomputadas isoladamente a partir só do
      timestamp da amostra (sem acesso a nenhuma outra linha do dataframe) —
      por construção não podem enxergar o dia D, pois não enxergam nada além do
      próprio instante.
    - is_dst_transition: é dado propagado do parquet de entrada, não derivado
      aqui — comparado contra o próprio valor de entrada.
    - lags e médias móveis: recomputados usando SOMENTE os dados com
      din_instante < 00:00 do dia da amostra (corte day-ahead), usando as MESMAS
      funções da geração real. Se o valor recalculado sobre o recorte truncado
      divergir do valor calculado sobre a série inteira, a série inteira usou
      informação que não existiria no momento da previsão — vazamento.
    """
    rng = np.random.default_rng(seed)
    indices = rng.choice(len(df), size=n_amostras, replace=False)

    colunas_calendario = [c for c in calcular_features_calendario(df.iloc[[0]]).columns]
    colunas_lags_medias = ["lag_24h", "lag_48h", "lag_168h", "lag_336h", "media_24h", "media_168h", "media_mesma_hora_7d"]
    colunas_testadas = colunas_calendario + ["dst_ativo", "is_feriado", "is_dst_transition"] + colunas_lags_medias

    divergencias = []
    n_comparacoes = 0

    for idx in indices:
        idx = int(idx)
        ts = df.loc[idx, "din_instante"]
        corte = pd.Timestamp(ts).normalize()

        # --- calendário / dst_ativo / is_feriado: recalculadas isoladas, sem
        # acesso a nenhuma outra linha
        ts_unico = pd.DataFrame({"din_instante": [ts]})
        calend_isolado = calcular_features_calendario(ts_unico).iloc[0].to_dict()
        calend_isolado["dst_ativo"] = calcular_dst_ativo(ts_unico["din_instante"]).iloc[0]
        calend_isolado["is_feriado"] = calcular_is_feriado(ts_unico["din_instante"]).iloc[0]
        calend_isolado["is_dst_transition"] = df.loc[idx, "is_dst_transition"]

        for col, valor_isolado in calend_isolado.items():
            valor_real = features.loc[idx, col]
            n_comparacoes += 1
            if not valores_equivalentes(valor_real, valor_isolado):
                divergencias.append(f"{col}@{ts} (isolado, sem histórico): full={valor_real!r} isolado={valor_isolado!r}")

        # --- lags e médias móveis: recalculados só com din_instante < corte, mais
        # a própria linha alvo com valor desconhecido (NaN) — nunca o valor real
        truncado = df.loc[df["din_instante"] < corte, ["din_instante", "val_cargaenergiahomwmed"]]
        linha_alvo = pd.DataFrame({"din_instante": [ts], "val_cargaenergiahomwmed": [np.nan]})
        recorte = pd.concat([truncado, linha_alvo], ignore_index=True)

        lags_recalc = calcular_lags(recorte).iloc[-1].to_dict()
        medias_recalc = calcular_medias_moveis(recorte).iloc[-1].to_dict()

        for col, valor_recalc in {**lags_recalc, **medias_recalc}.items():
            valor_real = features.loc[idx, col]
            n_comparacoes += 1
            if not valores_equivalentes(valor_real, valor_recalc):
                divergencias.append(f"{col}@{ts} (recorte truncado < {corte}): full={valor_real!r} recalculo={valor_recalc!r}")

    return {
        "n_timestamps_amostrados": n_amostras,
        "n_features_testadas": len(colunas_testadas),
        "colunas_testadas": colunas_testadas,
        "n_comparacoes": n_comparacoes,
        "divergencias": divergencias,
    }


# ---------------------------------------------------------------------------
def main():
    if not CARGA_SE_PATH.exists():
        raise SanityCheckError(f"Arquivo ausente: {CARGA_SE_PATH} (rode src/limpar.py primeiro).")

    df = pd.read_parquet(CARGA_SE_PATH)
    df = df.sort_values("din_instante").reset_index(drop=True)
    verificar_grade_regular(df)

    print("Calculando features de calendário...")
    calend = calcular_features_calendario(df)

    print("Calculando dst_ativo (zoneinfo/IANA)...")
    dst_ativo = calcular_dst_ativo(df["din_instante"])

    print("Calculando is_feriado (holidays, feriados nacionais)...")
    is_feriado = calcular_is_feriado(df["din_instante"])

    print("Calculando lags (>=24h)...")
    lags = calcular_lags(df)

    print("Calculando médias móveis (corte D-1)...")
    medias = calcular_medias_moveis(df)

    regime = pd.DataFrame({
        "dst_ativo": dst_ativo.values,
        "is_dst_transition": df["is_dst_transition"].values,
        "is_feriado": is_feriado.values,
    }, index=df.index)

    features = pd.concat([df[["din_instante"]], calend, regime, lags, medias], axis=1)
    if len(features) != len(df):
        raise SanityCheckError(f"Saída tem {len(features)} linhas, entrada tem {len(df)} — não pode haver remoção de linha.")

    print("\nVerificando NaN esperado (janela + NaN bruto propagado) para lags e médias móveis...")
    verificar_nan_esperado(df, features)
    print("  OK — NaN observado bate com o esperado em todas as 7 features (4 lags + 3 médias móveis).")

    print(f"\nTestando vazamento: {N_AMOSTRAS_VAZAMENTO} timestamps aleatórios (seed={SEED_VAZAMENTO})...")
    resultado = testar_vazamento(df, features, N_AMOSTRAS_VAZAMENTO, SEED_VAZAMENTO)

    if resultado["divergencias"]:
        print(f"\n{len(resultado['divergencias'])} DIVERGÊNCIA(S) DE VAZAMENTO ENCONTRADA(S):", file=sys.stderr)
        for d in resultado["divergencias"]:
            print(f"  - {d}", file=sys.stderr)
        raise SanityCheckError(
            f"Teste de vazamento falhou: {len(resultado['divergencias'])} de {resultado['n_comparacoes']} "
            "comparações divergiram. ABORTADO — nenhum arquivo escrito."
        )

    # --- gravação (só chega aqui se o teste de vazamento passou)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    features.to_parquet(OUT_PATH, index=False)

    # --- resumo no stdout
    print("\n=== RESUMO ===")
    print(f"Arquivo: {OUT_PATH}")
    print(f"Linhas: {len(features)}")
    print(f"Colunas: {len(features.columns)}")
    print("\nFeatures criadas e contagem de NaN:")
    for col in features.columns:
        if col == "din_instante":
            continue
        n_nan = int(features[col].isna().sum())
        print(f"  {col}: {n_nan} NaN")
    print("\nGate de NaN esperado (janela + NaN bruto propagado): OK, 0 divergências em lag_24h/48h/168h/336h e media_24h/168h/mesma_hora_7d.")

    print("\n=== TESTE DE VAZAMENTO ===")
    print(f"Timestamps amostrados: {resultado['n_timestamps_amostrados']} (seed={SEED_VAZAMENTO})")
    print(f"Features testadas: {resultado['n_features_testadas']} ({', '.join(resultado['colunas_testadas'])})")
    print(f"Comparações totais: {resultado['n_comparacoes']}")
    print("Divergências: 0")
    print("RESULTADO: nenhum vazamento encontrado — todas as features recomputadas a partir de dado truncado (< 00:00 do dia D) batem com o valor calculado sobre a série inteira.")
    print("\nTodos os sanity checks passaram.")


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
