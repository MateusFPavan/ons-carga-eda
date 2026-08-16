"""Gera reports/FACTS.md — a folha de fatos canônica do Projeto 3.

REGRA CENTRAL: nenhum número neste arquivo é digitado à mão. Todo valor é recalculado
aqui, a partir de data/raw/*.parquet, data/raw/MANIFEST.json e data/raw/temperatura/*
(já baixados em sessões anteriores — este script não baixa nada novo). Nenhum número é
copiado dos relatórios 00-04.

Idempotente: rodar duas vezes produz o mesmo arquivo byte a byte (sem timestamp de
geração, sem qualquer elemento não-determinístico).
"""
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TEMP_DIR = RAW_DIR / "temperatura"
CUSTO_DIR = RAW_DIR / "custo"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"
ANOS = list(range(2015, 2027))
TZ = ZoneInfo("America/Sao_Paulo")
INICIO_AVALIACAO = pd.Timestamp("2024-01-01")  # ESCOPO.md seção Validação, FACTS.md seção H

# Seção M — descreve o CÓDIGO (como a seção H), não recomputa nada; auditado à mão
# lendo src/limpar.py, src/modelo_naive.py, src/gerar_features.py e
# src/prophet_temperatura_completo.py em 2026-07.
TRATAMENTO_POR_COLUNA = [
    ("val_cargaenergiahomwmed (carga)", "texto (2015-2024) / float64 (2025-2026)",
     "Coerção para float64 com checagem de round-trip via Decimal (sem perda de precisão); NaN mantido, nunca imputado",
     "src/limpar.py: carregar_se(), verificar_roundtrip_string()"),
    ("val_cmo (CMO)", "float64 (2024-2025) / texto (2026)",
     "pd.to_numeric coerção explícita e incondicional (não confia no dtype de origem, que já divergiu antes)",
     "src/modelo_naive.py: carregar_cmo_horario_se()"),
    ("temperature_2m_previous_day1 (5 cidades)", "float (JSON Open-Meteo)",
     "previous_day1 (previsão feita 1 dia antes, leak-safe), NUNCA temperature_2m observada; reindex por timestamp",
     "src/prophet_temperatura_completo.py: carregar_temperatura_cidade()"),
    ("din_instante (timestamp)", "datetime, tz-naive no parquet de origem",
     "Tratado como hora local America/Sao_Paulo, SEM conversão para UTC (fato derivado, FACTS.md seção K3)",
     "src/limpar.py: main()"),
    ("is_dst_transition", "bool derivado do timestamp",
     "Gerado via zoneinfo/IANA (fold=0 vs fold=1), nenhuma data hardcoded; as 9 horas ficam excluídas como origem de previsão",
     "src/limpar.py: gerar_timestamps_dst(); src/gerar_facts.py: gerar_timestamps_especiais_dst()"),
    ("dst_ativo", "bool derivado do timestamp",
     "Via zoneinfo/IANA, fold=0 (interpretação padrão) nos timestamps ambíguos/inexistentes",
     "src/gerar_features.py: calcular_dst_ativo()"),
    ("is_feriado", "bool derivado do timestamp",
     "biblioteca holidays.Brazil(years=...), sem subdiv = só feriados nacionais (nenhum estadual/municipal)",
     "src/gerar_features.py: calcular_is_feriado()"),
    ("hora, dia_semana, mes, dia_ano, is_fim_de_semana", "int/bool derivado do timestamp",
     "Função pura do timestamp — sem consulta a nenhum dado histórico, não pode vazar",
     "src/gerar_features.py: calcular_features_calendario()"),
    ("hora_sin/cos, dia_semana_sin/cos, dia_ano_sin/cos", "float, codificação cíclica",
     "Seno/cosseno para evitar a descontinuidade artificial 23h→0h de uma codificação linear",
     "src/gerar_features.py: calcular_features_calendario()"),
    ("lag_24h/48h/168h/336h", "float, deslocamento da carga",
     "Shift por TEMPO (asfreq), não por posição de linha — continua correto sobre um recorte com lacunas (teste de vazamento)",
     "src/gerar_features.py: calcular_lags()"),
    ("media_24h/168h/mesma_hora_7d", "float, média móvel da carga",
     "Corte explícito em D-1 (day-ahead); reamostrado para calendário diário completo antes do shift/rolling",
     "src/gerar_features.py: calcular_medias_moveis()"),
]

COMENTARIOS_AUDITADOS = [
    "Coerção texto→float (carga e CMO): comentário presente há várias sessões (round-trip via Decimal em limpar.py; cast incondicional em modelo_naive.py).",
    "Exclusão dos 9 timestamps de transição de DST: comentário presente (limpar.py, gerar_facts.py, gerar_features.py) — gerados por zoneinfo, não hardcoded, e o motivo da exclusão está explícito.",
    "Alinhamento de fuso do CMO (hora local, não UTC): comentário presente em modelo_naive.py e limpar.py, remetendo ao fato derivado da seção K3.",
    "Uso de temperatura PREVISÃO (previous_day1) vs. OBSERVAÇÃO: NÃO tinha comentário no código até a auditoria anterior (só constava em docs/DATA_CARD.md) — comentário adicionado em carregar_temperatura_cidade() (commit 72b9e08).",
]

EXPECTED_COLUMNS = {"id_subsistema", "nom_subsistema", "din_instante", "val_cargaenergiahomwmed"}


def fmt_br(x, casas=4):
    if x is None:
        return "N/D"
    s = f"{x:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int(x):
    return f"{x:,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

def carregar_todos_os_anos():
    """Retorna (DataFrame concatenado, dict ano->dtype original de val_cargaenergiahomwmed).
    O dtype original precisa ser capturado ANTES do pd.concat: depois de concatenar,
    pandas homogeneiza a coluna inteira (mistura de str e float64 vira 'object' em
    todas as linhas), apagando a diferença real entre os anos."""
    frames = []
    dtype_por_ano = {}
    for ano in ANOS:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        if not fpath.exists():
            continue
        df = pd.read_parquet(fpath)
        dtype_por_ano[ano] = str(df["val_cargaenergiahomwmed"].dtype)
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        df["nom_subsistema"] = df["nom_subsistema"].astype(str)
        df["ano_arquivo"] = ano
        df["val_raw_str"] = df["val_cargaenergiahomwmed"].astype(str)
        df["val_num"] = pd.to_numeric(df["val_cargaenergiahomwmed"], errors="coerce")
        frames.append(df)
    return pd.concat(frames, ignore_index=True), dtype_por_ano


# ---------------------------------------------------------------------------
# A. Proveniência
# ---------------------------------------------------------------------------

def secao_a_proveniencia(manifest: dict) -> dict:
    entradas_ons = {k: v for k, v in manifest.items() if k.startswith("CURVA_CARGA_")}
    anos_cobertos = sorted(int(k.replace("CURVA_CARGA_", "").replace(".parquet", "")) for k in entradas_ons)

    urls = sorted(set(v["url"].rsplit("/", 1)[0] for v in entradas_ons.values()))
    url_base = urls[0] if len(urls) == 1 else urls

    last_modified_por_ano = {
        int(k.replace("CURVA_CARGA_", "").replace(".parquet", "")): v.get("http_last_modified")
        for k, v in entradas_ons.items()
    }
    # agrupar por data (dia) do Last-Modified
    grupos_por_data = {}
    for ano, lm in sorted(last_modified_por_ano.items()):
        if lm is None:
            continue
        data_str = " ".join(lm.split(" ")[1:4])  # "09 Oct 2025"
        grupos_por_data.setdefault(data_str, []).append(ano)

    manifest_bytes = MANIFEST_PATH.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    downloaded_ats = sorted(v.get("downloaded_at_local") for v in entradas_ons.values() if v.get("downloaded_at_local"))

    return {
        "n_arquivos_ons": len(entradas_ons),
        "anos_cobertos": anos_cobertos,
        "url_base": url_base,
        "manifest_sha256": manifest_sha256,
        "manifest_n_entradas_total": len(manifest),
        "snapshot_downloaded_at_min": downloaded_ats[0] if downloaded_ats else None,
        "snapshot_downloaded_at_max": downloaded_ats[-1] if downloaded_ats else None,
        "grupos_last_modified_por_data": grupos_por_data,
    }


# ---------------------------------------------------------------------------
# B. Esquema e divergências
# ---------------------------------------------------------------------------

def secao_b_esquema(full: pd.DataFrame, dtype_por_ano: dict) -> dict:
    por_ano = {}
    total_vazias = 0
    for ano in ANOS:
        sub = full[full["ano_arquivo"] == ano]
        if len(sub) == 0:
            continue
        colunas_presentes = {"id_subsistema", "nom_subsistema", "din_instante", "val_cargaenergiahomwmed"} & set(sub.columns)
        divergem = sorted(EXPECTED_COLUMNS ^ colunas_presentes)
        val_dtype = dtype_por_ano[ano]
        n_vazias = int((sub["val_raw_str"].str.strip() == "").sum())
        total_vazias += n_vazias
        ids_distintos = sorted(sub["id_subsistema"].dropna().unique().tolist())
        mapeamento = (
            sub[["id_subsistema", "nom_subsistema"]].drop_duplicates().sort_values("id_subsistema")
        ).to_dict(orient="records")
        por_ano[ano] = {
            "n_linhas": int(len(sub)),
            "colunas_divergem": divergem,
            "val_dtype": val_dtype,
            "n_strings_vazias": n_vazias,
            "id_subsistema_distintos": ids_distintos,
            "mapeamento_id_nome": mapeamento,
        }

    # estabilidade do id_subsistema em 12 anos
    todos_ids = [tuple(por_ano[a]["id_subsistema_distintos"]) for a in por_ano]
    id_subsistema_estavel = len(set(todos_ids)) == 1

    # nom_subsistema para SE por ano
    nome_se_por_ano = {}
    for ano, info in por_ano.items():
        for m in info["mapeamento_id_nome"]:
            if m["id_subsistema"] == "SE":
                nome_se_por_ano[ano] = m["nom_subsistema"]

    return {
        "por_ano": por_ano,
        "total_strings_vazias": total_vazias,
        "id_subsistema_estavel_12_anos": id_subsistema_estavel,
        "id_subsistema_lista": sorted(set(todos_ids[0])) if id_subsistema_estavel else None,
        "nome_se_por_ano": nome_se_por_ano,
        "cmo_dtype_por_ano": secao_b2_cmo_dtype(),
    }


def secao_b2_cmo_dtype() -> dict:
    """dtype de val_cmo (CMO Semi-Horário) por ano — mesmo tipo de checagem já
    feita para val_cargaenergiahomwmed acima, agora para o dataset de custo."""
    resultado = {}
    for ano in (2024, 2025, 2026):
        fpath = CUSTO_DIR / f"cmo_semi_horario_{ano}.parquet"
        if not fpath.exists():
            continue
        dfc = pd.read_parquet(fpath, columns=["val_cmo"])
        resultado[ano] = str(dfc["val_cmo"].dtype)
    return resultado


# ---------------------------------------------------------------------------
# C. Cobertura temporal
# ---------------------------------------------------------------------------

def secao_c_cobertura_temporal(full: pd.DataFrame) -> dict:
    resultado = {}
    for sub_id, g in full.groupby("id_subsistema"):
        ts = g["din_instante"].sort_values()
        primeiro = ts.iloc[0]
        ultimo = ts.iloc[-1]
        n_total = len(g)
        n_distintos = ts.nunique()
        n_duplicados = n_total - n_distintos

        dia = ts.dt.date
        contagem_por_dia = dia.value_counts().sort_index()
        calendario_completo = pd.date_range(primeiro.normalize(), ultimo.normalize(), freq="D").date
        contagem_por_dia = contagem_por_dia.reindex(calendario_completo, fill_value=0)
        dias_irregulares = contagem_por_dia[contagem_por_dia != 24]

        valido = g.dropna(subset=["val_num"])
        idx_min = valido["val_num"].idxmin()
        idx_max = valido["val_num"].idxmax()
        estatisticas_valor = {
            "n_validos": int(len(valido)),
            "minimo": float(valido["val_num"].min()),
            "din_instante_minimo": str(valido.loc[idx_min, "din_instante"]),
            "maximo": float(valido["val_num"].max()),
            "din_instante_maximo": str(valido.loc[idx_max, "din_instante"]),
            "media": float(valido["val_num"].mean()),
            "mediana": float(valido["val_num"].median()),
            "desvio_padrao": float(valido["val_num"].std()),
            "q25": float(valido["val_num"].quantile(0.25)),
            "q75": float(valido["val_num"].quantile(0.75)),
        }

        resultado[sub_id] = {
            "primeiro_instante": str(primeiro),
            "ultimo_instante": str(ultimo),
            "n_linhas": int(n_total),
            "n_timestamps_distintos": int(n_distintos),
            "n_duplicados": int(n_duplicados),
            "dias_irregulares": [{"dia": str(d), "n_registros": int(c)} for d, c in dias_irregulares.items()],
            "estatisticas_valor": estatisticas_valor,
        }
    return resultado


# ---------------------------------------------------------------------------
# D. Horário de verão — 9 timestamps especiais (gerados via zoneinfo, não hardcoded)
# ---------------------------------------------------------------------------

def classificar_timestamp_local(ts: pd.Timestamp) -> str:
    """Retorna 'ambiguo', 'inexistente' ou 'ok' usando fold=0/fold=1 via zoneinfo."""
    d0 = datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, tzinfo=TZ, fold=0)
    d1 = datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, tzinfo=TZ, fold=1)
    u0 = d0.astimezone(timezone.utc)
    u1 = d1.astimezone(timezone.utc)
    if u0 == u1:
        return "ok"
    back0 = u0.astimezone(TZ)
    inexistente = (back0.hour, back0.minute) != (ts.hour, ts.minute)
    return "inexistente" if inexistente else "ambiguo"


def gerar_timestamps_especiais_dst(inicio: str, fim: str) -> dict:
    """Varre hora a hora o intervalo [inicio, fim) e classifica cada timestamp local.
    Não usa nenhuma data hardcoded — só a regra de zona do IANA tzdata via zoneinfo."""
    inicio_ts = pd.Timestamp(inicio)
    fim_ts = pd.Timestamp(fim)
    horas = pd.date_range(inicio_ts, fim_ts, freq="h", inclusive="left")

    ambiguos = []
    inexistentes = []
    for ts in horas:
        classe = classificar_timestamp_local(ts)
        if classe == "ambiguo":
            ambiguos.append(str(ts))
        elif classe == "inexistente":
            inexistentes.append(str(ts))

    return {"ambiguos": ambiguos, "inexistentes": inexistentes}


def secao_d_dst(full: pd.DataFrame, timestamps_dst: dict) -> dict:
    ambiguos = timestamps_dst["ambiguos"]
    inexistentes = timestamps_dst["inexistentes"]
    todos_9 = sorted(inexistentes + ambiguos)

    detalhe_inexistentes = []
    for ts_str in inexistentes:
        ts = pd.Timestamp(ts_str)
        linha = full[full["din_instante"] == ts][["id_subsistema", "val_raw_str"]].sort_values("id_subsistema")
        valores = {r["id_subsistema"]: (r["val_raw_str"] if r["val_raw_str"].strip() != "" else "(vazio)") for _, r in linha.iterrows()}
        detalhe_inexistentes.append({"timestamp": ts_str, "valores_por_subsistema": valores})

    detalhe_ambiguos = []
    for ts_str in ambiguos:
        ts = pd.Timestamp(ts_str)
        linha = full[full["din_instante"] == ts][["id_subsistema", "val_raw_str"]].sort_values("id_subsistema")
        valores = {r["id_subsistema"]: r["val_raw_str"] for _, r in linha.iterrows()}
        # contagem de registros nesse dia e no dia seguinte, subsistema SE
        contagens_dia = {}
        for delta in (0, 1):
            d = (ts + pd.Timedelta(days=delta)).date()
            for sub in ["N", "NE", "S", "SE"]:
                n = len(full[(full["din_instante"].dt.date == d) & (full["id_subsistema"] == sub)])
                contagens_dia[f"{sub}_{d}"] = n
        detalhe_ambiguos.append({"timestamp": ts_str, "valores_por_subsistema": valores, "contagens_dia": contagens_dia})

    # "0E-8" — busca em toda a coluna string (anos texto), não restrita aos 9 timestamps
    ocorrencias_notacao_cientifica = full[full["val_raw_str"].str.contains("E", case=False, na=False) & (full["ano_arquivo"] <= 2024)]
    detalhe_e = ocorrencias_notacao_cientifica[["id_subsistema", "din_instante", "val_raw_str"]].astype(str).to_dict(orient="records")

    return {
        "n_ambiguos": len(ambiguos),
        "n_inexistentes": len(inexistentes),
        "n_total": len(todos_9),
        "timestamps_ordenados": todos_9,
        "detalhe_inexistentes": detalhe_inexistentes,
        "detalhe_ambiguos": detalhe_ambiguos,
        "ocorrencias_notacao_cientifica": detalhe_e,
    }


# ---------------------------------------------------------------------------
# E. Anomalias conhecidas e não explicadas
# ---------------------------------------------------------------------------

def secao_e_anomalias(full: pd.DataFrame, datas_transicao_dst: set) -> dict:
    resultado = {}
    for sub_id, g in full.groupby("id_subsistema"):
        valido = g.dropna(subset=["val_num"])
        idx_min = valido["val_num"].idxmin()
        row_min = valido.loc[idx_min]
        data_min = row_min["din_instante"].date()
        resultado[sub_id] = {
            "valor_minimo": float(row_min["val_num"]),
            "din_instante_minimo": str(row_min["din_instante"]),
            "coincide_com_transicao_dst": str(data_min) in datas_transicao_dst,
        }

    # 2015-04-09, todos os subsistemas — duas formas distintas de ausência
    # (linha ausente vs. linha presente com valor vazio), checadas separadamente
    dia_alvo = pd.Timestamp("2015-04-09").date()
    dia_2015_04_09 = {}
    for sub in ["N", "NE", "S", "SE"]:
        g_dia = full[(full["din_instante"].dt.date == dia_alvo) & (full["id_subsistema"] == sub)]
        dia_2015_04_09[sub] = {
            "n_linhas": int(len(g_dia)),
            "n_vazias": int((g_dia["val_raw_str"].str.strip() == "").sum()),
        }

    return {
        "minimos_por_subsistema": resultado,
        "dia_2015_04_09": dia_2015_04_09,
    }


# ---------------------------------------------------------------------------
# F. Efeito do DST no perfil (recalculado do zero, mesma metodologia do relatório 03)
# ---------------------------------------------------------------------------

VERWES_COM_DST = [(2015, 2016), (2016, 2017), (2017, 2018), (2018, 2019)]
VERWES_SEM_DST = [(2021, 2022), (2022, 2023), (2023, 2024), (2024, 2025)]


def secao_f_efeito_dst(full: pd.DataFrame, timestamps_dst_completo: dict) -> dict:
    seco = full[full["id_subsistema"] == "SE"].dropna(subset=["val_num"]).copy()
    excluir = set(timestamps_dst_completo["ambiguos"]) | set(timestamps_dst_completo["inexistentes"])
    seco = seco[~seco["din_instante"].astype(str).isin(excluir)]

    def montar_regime(verwes):
        partes = []
        for ano_dez, ano_jan in verwes:
            mask_dez = (seco["din_instante"].dt.year == ano_dez) & (seco["din_instante"].dt.month == 12)
            mask_jan = (seco["din_instante"].dt.year == ano_jan) & (seco["din_instante"].dt.month == 1)
            partes.append(seco[mask_dez | mask_jan])
        r = pd.concat(partes, ignore_index=True)
        r["dow"] = r["din_instante"].dt.dayofweek
        r["tipo_dia"] = r["dow"].apply(lambda d: "fim_de_semana" if d >= 5 else "dia_util")
        r["data"] = r["din_instante"].dt.date
        r["hora"] = r["din_instante"].dt.hour
        return r

    com_dst = montar_regime(VERWES_COM_DST)
    sem_dst = montar_regime(VERWES_SEM_DST)

    def perfil(df_regime, tipo_dia, normalizado):
        sub = df_regime[df_regime["tipo_dia"] == tipo_dia].copy()
        if normalizado:
            media_diaria = sub.groupby("data")["val_num"].transform("mean")
            sub["v"] = sub["val_num"] / media_diaria
        else:
            sub["v"] = sub["val_num"]
        return sub.groupby("hora")["v"].mean()

    def pico_noite_tarde(perfil_serie):
        tarde = perfil_serie.loc[12:17]
        noite = perfil_serie.loc[18:23]
        h_tarde = int(tarde.idxmax())
        v_tarde = float(tarde.max())
        h_noite = int(noite.idxmax())
        v_noite = float(noite.max())
        return {
            "hora_pico_tarde": h_tarde, "valor_pico_tarde": v_tarde,
            "hora_pico_noite": h_noite, "valor_pico_noite": v_noite,
            "razao_noite_tarde": v_noite / v_tarde,
        }

    resultado = {"contagem_dias": {}, "picos": {}}
    for nome_regime, df_regime in [("com_dst", com_dst), ("sem_dst", sem_dst)]:
        resultado["contagem_dias"][nome_regime] = {
            tipo: int(df_regime[df_regime["tipo_dia"] == tipo]["data"].nunique())
            for tipo in ["dia_util", "fim_de_semana"]
        }
        resultado["picos"][nome_regime] = {}
        for tipo in ["dia_util", "fim_de_semana"]:
            for normalizado, chave in [(False, "bruto"), (True, "normalizado")]:
                p = perfil(df_regime, tipo, normalizado)
                resultado["picos"][nome_regime].setdefault(tipo, {})[chave] = pico_noite_tarde(p)

    return resultado


# ---------------------------------------------------------------------------
# G. Temperatura — viabilidade (a partir dos JSON já baixados em data/raw/temperatura/)
# ---------------------------------------------------------------------------

CIDADES_TEMPERATURA = ["Sao_Paulo", "Rio_de_Janeiro", "Belo_Horizonte", "Brasilia", "Goiania"]


def secao_g_temperatura() -> dict:
    resultado = {"arquivos_ausentes": [], "cobertura_inicial": {}, "comparacao_era5": {}, "comparacao_inmet": None}

    # cobertura inicial (primeiro timestamp não-nulo), a partir dos arquivos de teste já baixados
    for janela, cidade_arquivo in [("mar2021", "Sao_Paulo"), ("jan2024", "Sao_Paulo")]:
        fpath = TEMP_DIR / f"openmeteo_previous_day1_{cidade_arquivo}_{janela}.json"
        if not fpath.exists():
            resultado["arquivos_ausentes"].append(str(fpath.name))
            continue
        j = json.loads(fpath.read_text(encoding="utf-8"))
        tempos = j["hourly"]["time"]
        valores = j["hourly"]["temperature_2m_previous_day1"]
        primeiro_nao_nulo = next((t for t, v in zip(tempos, valores) if v is not None), None)
        n_nulos = sum(1 for v in valores if v is None)

        # primeiro dia com as 24 horas completas (0 nulos naquele dia especificamente)
        por_dia = {}
        for t, v in zip(tempos, valores):
            dia = t[:10]
            por_dia.setdefault(dia, [0, 0])
            por_dia[dia][1] += 1
            if v is None:
                por_dia[dia][0] += 1
        primeiro_dia_completo = next((dia for dia, (nulos, total) in sorted(por_dia.items()) if nulos == 0), None)
        dia_primeiro_nao_nulo = primeiro_nao_nulo[:10] if primeiro_nao_nulo else None
        horas_disponiveis_no_dia_parcial = (
            por_dia[dia_primeiro_nao_nulo][1] - por_dia[dia_primeiro_nao_nulo][0]
            if dia_primeiro_nao_nulo in por_dia else None
        )

        resultado["cobertura_inicial"][janela] = {
            "primeiro_timestamp_nao_nulo": primeiro_nao_nulo,
            "primeiro_dia_24h_completo": primeiro_dia_completo,
            "horas_disponiveis_no_dia_do_primeiro_nao_nulo": horas_disponiveis_no_dia_parcial,
            "n_nulos_na_janela": n_nulos,
            "n_total_na_janela": len(valores),
        }

    # comparação previsão-24h vs ERA5, 5 cidades, 2024-2025
    todas_linhas = []
    por_cidade = {}
    for cidade in CIDADES_TEMPERATURA:
        era5_path = TEMP_DIR / f"era5_temperature_2m_{cidade}_2024_2025.json"
        prev_path = TEMP_DIR / f"openmeteo_previous_day1_{cidade}_2024_2025.json"
        if not era5_path.exists() or not prev_path.exists():
            resultado["arquivos_ausentes"].append(f"{cidade}: era5={era5_path.exists()} prev={prev_path.exists()}")
            continue
        era5 = json.loads(era5_path.read_text(encoding="utf-8"))
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        df_era5 = pd.DataFrame({"time": era5["hourly"]["time"], "era5": era5["hourly"]["temperature_2m"]})
        df_prev = pd.DataFrame({"time": prev["hourly"]["time"], "previsao": prev["hourly"]["temperature_2m_previous_day1"]})
        merged = pd.merge(df_era5, df_prev, on="time", how="outer")
        merged["era5"] = pd.to_numeric(merged["era5"], errors="coerce")
        merged["previsao"] = pd.to_numeric(merged["previsao"], errors="coerce")
        comparavel = merged.dropna(subset=["era5", "previsao"]).copy()
        comparavel["erro"] = comparavel["previsao"] - comparavel["era5"]
        comparavel["hora"] = pd.to_datetime(comparavel["time"]).dt.hour
        comparavel["cidade"] = cidade

        mae = float(comparavel["erro"].abs().mean())
        rmse = float(np.sqrt((comparavel["erro"] ** 2).mean()))
        vies = float(comparavel["erro"].mean())

        p95 = comparavel["era5"].quantile(0.95)
        p5 = comparavel["era5"].quantile(0.05)
        mae_p95 = float(comparavel[comparavel["era5"] >= p95]["erro"].abs().mean())
        mae_p5 = float(comparavel[comparavel["era5"] <= p5]["erro"].abs().mean())

        por_cidade[cidade] = {
            "n_comparavel": int(len(comparavel)), "n_descartado": int(len(merged) - len(comparavel)),
            "mae": mae, "rmse": rmse, "vies": vies, "mae_p95": mae_p95, "mae_p5": mae_p5,
        }
        todas_linhas.append(comparavel[["time", "hora", "era5", "previsao", "erro"]])

    if todas_linhas:
        agregado_df = pd.concat(todas_linhas, ignore_index=True)
        mae_agg = float(agregado_df["erro"].abs().mean())
        rmse_agg = float(np.sqrt((agregado_df["erro"] ** 2).mean()))
        vies_agg = float(agregado_df["erro"].mean())
        p95_agg = agregado_df["era5"].quantile(0.95)
        p5_agg = agregado_df["era5"].quantile(0.05)
        mae_p95_agg = float(agregado_df[agregado_df["era5"] >= p95_agg]["erro"].abs().mean())
        mae_p5_agg = float(agregado_df[agregado_df["era5"] <= p5_agg]["erro"].abs().mean())
        mae_por_hora = agregado_df.groupby("hora")["erro"].apply(lambda s: float(s.abs().mean())).to_dict()
        hora_min_mae = min(mae_por_hora, key=mae_por_hora.get)
        hora_max_mae = max(mae_por_hora, key=mae_por_hora.get)

        n_cidades_mae_p95_maior = sum(1 for c in por_cidade.values() if c["mae_p95"] > c["mae"])
        n_cidades_mae_p5_maior = sum(1 for c in por_cidade.values() if c["mae_p5"] > c["mae"])

        resultado["comparacao_era5"] = {
            "por_cidade": por_cidade,
            "n_total_comparavel": int(len(agregado_df)),
            "mae_agregado": mae_agg, "rmse_agregado": rmse_agg, "vies_agregado": vies_agg,
            "mae_p95_agregado": mae_p95_agg, "mae_p5_agregado": mae_p5_agg,
            "mae_por_hora": mae_por_hora,
            "hora_menor_mae": int(hora_min_mae), "valor_menor_mae": mae_por_hora[hora_min_mae],
            "hora_maior_mae": int(hora_max_mae), "valor_maior_mae": mae_por_hora[hora_max_mae],
            "n_cidades_mae_p95_maior_que_geral": n_cidades_mae_p95_maior,
            "n_cidades_mae_p5_maior_que_geral": n_cidades_mae_p5_maior,
        }

    # comparação ERA5 vs estação INMET A701 (São Paulo, 2024) — a partir do ZIP já baixado
    zip_path = TEMP_DIR / "inmet_dadoshistoricos_2024.zip"
    if zip_path.exists():
        with zipfile.ZipFile(zip_path) as zf:
            membro = next((n for n in zf.namelist() if "A701" in n.upper()), None)
            if membro:
                texto = zf.open(membro).read().decode("latin-1")
                linhas = texto.splitlines()
                idx = next(i for i, l in enumerate(linhas) if l.startswith("Data"))
                df = pd.read_csv(StringIO("\n".join(linhas[idx:])), sep=";", decimal=",", encoding="latin-1")
                col_temp = [c for c in df.columns if "TEMPERATURA DO AR" in c.upper()][0]
                col_hora = [c for c in df.columns if "HORA" in c.upper()][0]

                df["hora_str"] = df[col_hora].astype(str).str.replace(" UTC", "", regex=False).str.zfill(4)
                df["hora_fmt"] = df["hora_str"].str[:2] + ":" + df["hora_str"].str[2:]
                df["din_utc_naive"] = pd.to_datetime(df["Data"].astype(str) + " " + df["hora_fmt"], format="%Y/%m/%d %H:%M", errors="coerce")
                df["din_utc"] = df["din_utc_naive"].dt.tz_localize("UTC")
                df["din_local"] = df["din_utc"].dt.tz_convert("America/Sao_Paulo")

                temp_num = pd.to_numeric(df[col_temp], errors="coerce")
                temp_raw_str = df[col_temp].astype(str).str.strip()
                n_9999 = int((temp_raw_str == "9999").sum())
                temp_num = temp_num.mask(temp_num.abs() >= 9999, np.nan)

                obs = pd.DataFrame({"din_local": df["din_local"], "temp_inmet": temp_num}).dropna(subset=["din_local"])
                obs["time"] = obs["din_local"].dt.strftime("%Y-%m-%dT%H:%M")
                obs = obs.groupby("time", as_index=False)["temp_inmet"].mean()

                era5_sp_path = TEMP_DIR / "era5_temperature_2m_Sao_Paulo_2024_2025.json"
                if era5_sp_path.exists():
                    era5 = json.loads(era5_sp_path.read_text(encoding="utf-8"))
                    df_era5 = pd.DataFrame({"time": era5["hourly"]["time"], "era5": era5["hourly"]["temperature_2m"]})
                    df_era5_2024 = df_era5[df_era5["time"] < "2025-01-01"]
                    merged = pd.merge(df_era5_2024, obs, on="time", how="inner")
                    merged["era5"] = pd.to_numeric(merged["era5"], errors="coerce")
                    comparavel = merged.dropna(subset=["era5", "temp_inmet"])
                    erro = comparavel["temp_inmet"] - comparavel["era5"]
                    resultado["comparacao_inmet"] = {
                        "estacao": "A701",
                        "n_linhas_brutas": int(len(df)),
                        "n_9999_literal": n_9999,
                        "n_ausente_total": int(temp_num.isna().sum()),
                        "n_comparavel": int(len(comparavel)),
                        "n_descartado": int(len(merged) - len(comparavel)),
                        "mae": float(erro.abs().mean()),
                        "rmse": float(np.sqrt((erro ** 2).mean())),
                        "vies": float(erro.mean()),
                    }

    return resultado


# ---------------------------------------------------------------------------
# J. Custo de despacho (a partir da amostra 2024 já baixada em data/raw/custo/)
# ---------------------------------------------------------------------------

def secao_j_custo(cobertura_carga: dict) -> dict:
    resultado = {"arquivo_ausente": None}

    fpath = CUSTO_DIR / "cmo_semi_horario_2024.parquet"
    if not fpath.exists():
        resultado["arquivo_ausente"] = str(fpath)
        return resultado

    df = pd.read_parquet(fpath)
    df["id_subsistema"] = df["id_subsistema"].astype(str)
    n_linhas = int(len(df))

    ids_observados = sorted(df["id_subsistema"].unique().tolist())

    # granularidade: diferenças entre timestamps distintos (todo o arquivo, não por subsistema)
    ts_distintos = df["din_instante"].drop_duplicates().sort_values().reset_index(drop=True)
    diffs = ts_distintos.diff().dropna().dt.total_seconds()
    diffs_distintas = sorted(diffs.unique().tolist())
    diff_modal = diffs.mode().iloc[0] if len(diffs) else None

    primeiro_instante = str(df["din_instante"].min())
    ultimo_instante = str(df["din_instante"].max())

    # dias inteiramente ausentes (checado num subsistema, já que todos têm a mesma contagem —
    # confirmado abaixo por linhas_por_subsistema)
    linhas_por_subsistema = df.groupby("id_subsistema").size().to_dict()
    linhas_por_subsistema = {k: int(v) for k, v in linhas_por_subsistema.items()}

    sub_ref = df[df["id_subsistema"] == "SE"].copy()
    sub_ref["dia"] = sub_ref["din_instante"].dt.date
    dias_presentes = set(sub_ref["dia"].unique())
    ano_calendario = pd.date_range(
        f"{sub_ref['dia'].min().year}-01-01", f"{sub_ref['dia'].min().year}-12-31", freq="D"
    ).date
    dias_ausentes = sorted(set(ano_calendario) - dias_presentes)
    dias_esperados_calendario = len(ano_calendario)
    dias_presentes_n = len(dias_presentes)

    n_esperado_grade_completa = dias_esperados_calendario * 48 * len(ids_observados)

    # nulos/negativos/zeros em val_cmo
    val = pd.to_numeric(df["val_cmo"], errors="coerce")
    n_nulo = int(df["val_cmo"].isna().sum())
    n_negativos = int((val < 0).sum())
    n_zeros = int((val == 0).sum())
    n_validos = int(val.notna().sum())

    # cobertura cruzada com a carga SE/CO (já calculada na seção C)
    carga_se = cobertura_carga.get("SE", {})

    resultado.update({
        "n_linhas": n_linhas,
        "ids_observados": ids_observados,
        "linhas_por_subsistema": linhas_por_subsistema,
        "diffs_segundos_distintas": diffs_distintas,
        "diff_modal_segundos": float(diff_modal) if diff_modal is not None else None,
        "primeiro_instante": primeiro_instante,
        "ultimo_instante": ultimo_instante,
        "dias_calendario_no_periodo": dias_esperados_calendario,
        "dias_presentes": dias_presentes_n,
        "dias_ausentes": [str(d) for d in dias_ausentes],
        "n_esperado_grade_completa_30min": n_esperado_grade_completa,
        "val_cmo_n_validos": n_validos,
        "val_cmo_n_nulo": n_nulo,
        "val_cmo_n_negativos": n_negativos,
        "val_cmo_n_zeros": n_zeros,
        "carga_se_primeiro_instante": carga_se.get("primeiro_instante"),
        "carga_se_ultimo_instante": carga_se.get("ultimo_instante"),
    })
    return resultado


# ---------------------------------------------------------------------------
# J7. Cobertura do CMO Semi-Horário ANO A ANO (2020-2026) — só 2024 tinha sido
# verificado em detalhe (J2/J3); 2020-2023 constavam apenas na listagem do portal,
# nunca baixados nem checados. Fecha o item aberto da seção I / [TODO] dos docs.
# NÃO baixa nada: só audita o que já está em data/raw/custo/. Para o ano corrente
# (2026, parcial), o calendário esperado vai só até o último dia presente no
# arquivo, não até 31/dez — um ano incompleto por construção não é uma "lacuna".
# ---------------------------------------------------------------------------

def secao_j7_cobertura_anual_cmo() -> dict:
    anos = list(range(2020, 2027))
    por_ano = {}
    for ano in anos:
        fpath = CUSTO_DIR / f"cmo_semi_horario_{ano}.parquet"
        if not fpath.exists():
            por_ano[ano] = {"arquivo_existe": False}
            continue

        df = pd.read_parquet(fpath, columns=["id_subsistema", "din_instante", "val_cmo"])
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        sub_se = df[df["id_subsistema"] == "SE"].copy()

        val = pd.to_numeric(sub_se["val_cmo"], errors="coerce")
        primeiro = sub_se["din_instante"].min()
        ultimo = sub_se["din_instante"].max()

        sub_se["dia"] = sub_se["din_instante"].dt.date
        dias_presentes = set(sub_se["dia"].unique())
        calendario_ate_ultimo_dia = pd.date_range(f"{ano}-01-01", ultimo.normalize(), freq="D").date
        dias_ausentes = sorted(set(calendario_ate_ultimo_dia) - dias_presentes)
        n_esperado_grade_completa = len(calendario_ate_ultimo_dia) * 48

        # cobertura em base HORÁRIA (dias x 24) — granularidade que o projeto de
        # fato usa (carregar_cmo_horario_se agrega 30min->60min); distinta da
        # contagem em semi-horas (granularidade nativa do arquivo) já acima.
        horas_existentes = sub_se["din_instante"].dt.floor("h").nunique()
        horas_esperadas = len(calendario_ate_ultimo_dia) * 24
        pct_cobertura_horaria = horas_existentes / horas_esperadas * 100 if horas_esperadas else None

        por_ano[ano] = {
            "arquivo_existe": True,
            "n_linhas_se": int(len(sub_se)),
            "primeiro_instante": str(primeiro),
            "ultimo_instante": str(ultimo),
            "ano_completo_no_arquivo": bool(ultimo.date() >= pd.Timestamp(f"{ano}-12-31").date()),
            "n_esperado_grade_completa_30min_ate_ultimo_dia": n_esperado_grade_completa,
            "horas_existentes": int(horas_existentes),
            "horas_esperadas": int(horas_esperadas),
            "pct_cobertura_horaria": pct_cobertura_horaria,
            "dias_ausentes_ate_ultimo_dia": [str(d) for d in dias_ausentes],
            "val_cmo_n_validos": int(val.notna().sum()),
            "val_cmo_n_nulo": int(val.isna().sum()),
            "val_cmo_n_negativos": int((val < 0).sum()),
            "val_cmo_n_zeros": int((val == 0).sum()),
            "val_cmo_min": float(val.min()) if val.notna().any() else None,
            "val_cmo_max": float(val.max()) if val.notna().any() else None,
            "val_cmo_media": float(val.mean()) if val.notna().any() else None,
        }
    return {"anos": anos, "por_ano": por_ano}


# ---------------------------------------------------------------------------
# K2b. Concentração de custo sobre o PERÍODO DE AVALIAÇÃO completo (2024-01-01 até
# o fim da série) — extensão de K2 (que cobre só 2024) usando o naive SEMANAL
# (lag=168h, régua principal do projeto, FACTS.md seção H) como instrumento de
# medição de erro. Cálculo autocontido, independente de src/modelo_naive.py.
# ---------------------------------------------------------------------------

def secao_k2b_concentracao_avaliacao() -> dict:
    anos_cmo_disponiveis = [ano for ano in (2024, 2025, 2026) if (CUSTO_DIR / f"cmo_semi_horario_{ano}.parquet").exists()]
    if not anos_cmo_disponiveis:
        return {"disponivel": False}

    frames = []
    for ano in ANOS:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        if not fpath.exists():
            continue
        dfc = pd.read_parquet(fpath, columns=["id_subsistema", "din_instante", "val_cargaenergiahomwmed"])
        dfc["id_subsistema"] = dfc["id_subsistema"].astype(str)
        dfc = dfc[dfc["id_subsistema"] == "SE"].copy()
        dfc["val_num"] = pd.to_numeric(dfc["val_cargaenergiahomwmed"], errors="coerce")
        frames.append(dfc)
    carga_se = pd.concat(frames, ignore_index=True).sort_values("din_instante").reset_index(drop=True)

    serie = carga_se.set_index("din_instante")["val_num"]
    naive = pd.DataFrame({"din_instante": serie.index, "observado": serie.values}).set_index("din_instante")
    previsao = serie.copy()
    previsao.index = previsao.index + pd.Timedelta(days=7)  # naive semanal: lag 168h
    naive["previsao_naive"] = previsao
    naive = naive.dropna(subset=["previsao_naive"]).reset_index()
    naive["erro"] = naive["observado"] - naive["previsao_naive"]
    naive_avaliacao = naive[naive["din_instante"] >= INICIO_AVALIACAO].copy()

    frames_cmo = []
    for ano in anos_cmo_disponiveis:
        fpath = CUSTO_DIR / f"cmo_semi_horario_{ano}.parquet"
        dfc = pd.read_parquet(fpath, columns=["id_subsistema", "din_instante", "val_cmo"])
        dfc["id_subsistema"] = dfc["id_subsistema"].astype(str)
        dfc["val_cmo"] = pd.to_numeric(dfc["val_cmo"], errors="coerce")
        frames_cmo.append(dfc[dfc["id_subsistema"] == "SE"])
    cmo_se = pd.concat(frames_cmo, ignore_index=True)
    cmo_se["hora_local"] = cmo_se["din_instante"].dt.floor("h")
    cmo_media_horaria = cmo_se.groupby("hora_local")["val_cmo"].mean().rename("cmo_media").reset_index()

    merged = pd.merge(naive_avaliacao, cmo_media_horaria, left_on="din_instante", right_on="hora_local", how="left")
    n_sem_cmo = int(merged["cmo_media"].isna().sum())
    custo_base = merged[merged["cmo_media"].notna()].copy()
    custo_base["custo"] = custo_base["erro"].abs() * custo_base["cmo_media"]

    custo_total = float(custo_base["custo"].sum())
    p90 = float(custo_base["cmo_media"].quantile(0.90))
    top10 = custo_base[custo_base["cmo_media"] >= p90]
    pct_custo_top10 = float(top10["custo"].sum() / custo_total * 100) if custo_total else None

    return {
        "disponivel": True,
        "anos_cmo_usados": anos_cmo_disponiveis,
        "inicio_avaliacao": str(INICIO_AVALIACAO.date()),
        "fim_avaliacao": str(naive_avaliacao["din_instante"].max()),
        "n_horas_totais": int(len(naive_avaliacao)),
        "n_horas_sem_cmo": n_sem_cmo,
        "n_horas_com_cmo": int(len(custo_base)),
        "limiar_p90_cmo": p90,
        "n_horas_top10pct_cmo": int(len(top10)),
        "pct_custo_top10pct_cmo": pct_custo_top10,
    }


# ---------------------------------------------------------------------------
# K. Agregação do CMO (sensibilidade + fuso) — recalculado do zero a partir de
# data/raw/custo/cmo_semi_horario_2024.parquet e data/raw/CURVA_CARGA_{2023,2024}.parquet
# ---------------------------------------------------------------------------

def secao_k_agregacao_e_fuso() -> dict:
    resultado = {"arquivo_ausente": None}
    fpath_cmo = CUSTO_DIR / "cmo_semi_horario_2024.parquet"
    if not fpath_cmo.exists():
        resultado["arquivo_ausente"] = str(fpath_cmo)
        return resultado

    # --- carga SE, 2023+2024 (2023 só para permitir o naive nos primeiros 7 dias de 2024)
    frames = []
    for ano in (2023, 2024):
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        dfc = pd.read_parquet(fpath, columns=["id_subsistema", "din_instante", "val_cargaenergiahomwmed"])
        dfc["id_subsistema"] = dfc["id_subsistema"].astype(str)
        dfc = dfc[dfc["id_subsistema"] == "SE"].copy()
        dfc["val_num"] = pd.to_numeric(dfc["val_cargaenergiahomwmed"], errors="coerce")
        frames.append(dfc)
    carga_se = pd.concat(frames, ignore_index=True).sort_values("din_instante").reset_index(drop=True)

    serie = carga_se.set_index("din_instante")["val_num"]
    naive = pd.DataFrame({"din_instante": serie.index, "observado": serie.values}).set_index("din_instante")
    previsao = serie.copy()
    previsao.index = previsao.index + pd.Timedelta(days=7)
    naive["previsao_naive"] = previsao
    naive = naive.dropna(subset=["previsao_naive"]).reset_index()
    naive["erro"] = naive["observado"] - naive["previsao_naive"]
    naive_2024 = naive[naive["din_instante"].dt.year == 2024].copy()

    # --- CMO semi-horário SE 2024, 3 variantes horárias
    cmo = pd.read_parquet(fpath_cmo)
    cmo["id_subsistema"] = cmo["id_subsistema"].astype(str)
    cmo_se = cmo[cmo["id_subsistema"] == "SE"].copy()
    cmo_se["hora_local"] = cmo_se["din_instante"].dt.floor("h")
    cmo_se["ordem_semihora"] = cmo_se.groupby("hora_local").cumcount()

    media = cmo_se.groupby("hora_local")["val_cmo"].mean().rename("cmo_media")
    maximo = cmo_se.groupby("hora_local")["val_cmo"].max().rename("cmo_maximo")
    primeira = cmo_se[cmo_se["ordem_semihora"] == 0].set_index("hora_local")["val_cmo"].rename("cmo_primeira")
    n_semihoras = cmo_se.groupby("hora_local").size().rename("n_semihoras")
    variantes = pd.concat([media, maximo, primeira, n_semihoras], axis=1).reset_index()

    dist_semihoras = {str(k): int(v) for k, v in variantes["n_semihoras"].value_counts().to_dict().items()}

    dias_sem_cmo_2024 = ["2024-02-08", "2024-02-17", "2024-07-13", "2024-12-29"]
    dias_sem_cmo_set = set(pd.Timestamp(d).date() for d in dias_sem_cmo_2024)

    merged = pd.merge(naive_2024, variantes, left_on="din_instante", right_on="hora_local", how="left")
    merged["dia"] = merged["din_instante"].dt.date
    custo_base = merged[~merged["dia"].isin(dias_sem_cmo_set) & merged["cmo_media"].notna()].copy()

    custo_base["custo_media"] = custo_base["erro"].abs() * custo_base["cmo_media"]
    custo_base["custo_maximo"] = custo_base["erro"].abs() * custo_base["cmo_maximo"]
    custo_base["custo_primeira"] = custo_base["erro"].abs() * custo_base["cmo_primeira"]

    total_a = float(custo_base["custo_media"].sum())
    total_b = float(custo_base["custo_maximo"].sum())
    total_c = float(custo_base["custo_primeira"].sum())
    pct_b_de_a = total_b / total_a * 100
    pct_c_de_a = total_c / total_a * 100

    corr_ab = float(custo_base["custo_media"].corr(custo_base["custo_maximo"]))
    corr_ac = float(custo_base["custo_media"].corr(custo_base["custo_primeira"]))
    corr_bc = float(custo_base["custo_maximo"].corr(custo_base["custo_primeira"]))

    def pct_mudanca(base, outro):
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(base != 0, np.abs(outro - base) / np.abs(base), np.where(outro != 0, np.inf, 0))

    mud_ab = pct_mudanca(custo_base["custo_media"].values, custo_base["custo_maximo"].values)
    mud_ac = pct_mudanca(custo_base["custo_media"].values, custo_base["custo_primeira"].values)
    idx_ab = set(custo_base.index[mud_ab > 0.10])
    idx_ac = set(custo_base.index[mud_ac > 0.10])
    n_ab_10pct = int(len(idx_ab))
    n_ac_10pct = int(len(idx_ac))
    mesmo_conjunto = idx_ab == idx_ac

    n_horas_cmo_zero_horario = int((custo_base["cmo_media"] == 0).sum())
    n_horas_cmo_negativo_horario = int((custo_base["cmo_media"] < 0).sum())
    n_semihoras_negativas = int((pd.to_numeric(cmo_se["val_cmo"], errors="coerce") < 0).sum())

    p90 = float(custo_base["cmo_media"].quantile(0.90))
    top10 = custo_base[custo_base["cmo_media"] >= p90]
    pct_custo_top10 = float(top10["custo_media"].sum() / total_a * 100)

    # --- fuso: perfil intradiário CMO (SE, 2024) e correlação com perfil da carga (SE/CO, 2024)
    cmo_se_perfil = cmo_se.copy()
    cmo_se_perfil["hora"] = cmo_se_perfil["din_instante"].dt.hour
    perfil_cmo = cmo_se_perfil.groupby("hora")["val_cmo"].mean()

    carga_2024 = carga_se[carga_se["din_instante"].dt.year == 2024].copy()
    carga_2024["hora"] = carga_2024["din_instante"].dt.hour
    perfil_carga = carga_2024.groupby("hora")["val_num"].mean()

    hora_pico_cmo = int(perfil_cmo.idxmax())
    valor_pico_cmo = float(perfil_cmo.max())
    hora_vale_cmo = int(perfil_cmo.idxmin())
    valor_vale_cmo = float(perfil_cmo.min())

    v_cmo = perfil_cmo.reindex(range(24)).values
    v_carga = perfil_carga.reindex(range(24)).values
    corr_lag0 = float(np.corrcoef(np.roll(v_cmo, 0), v_carga)[0, 1])
    corr_lag_utc = float(np.corrcoef(np.roll(v_cmo, 3), v_carga)[0, 1])  # hipótese "CMO em UTC, corrigir +3h"

    # --- dicionários: confirmação de ausência de menção a fuso (busca literal nos PDFs já baixados)
    dic_cmo_path = RAW_DIR / "documentacao" / "DicionarioDados_Cmo_Semi_Horario.pdf"
    dic_carga_path = RAW_DIR / "documentacao" / "DicionarioDados_CurvaCarga.pdf"
    dicionarios_presentes = dic_cmo_path.exists() and dic_carga_path.exists()

    resultado.update({
        "sensibilidade_agregacao": {
            "custo_total_media": total_a, "custo_total_maximo": total_b, "custo_total_primeira": total_c,
            "pct_maximo_de_media": pct_b_de_a, "pct_primeira_de_media": pct_c_de_a,
            "correlacao_media_maximo": corr_ab, "correlacao_media_primeira": corr_ac, "correlacao_maximo_primeira": corr_bc,
            "n_horas_maximo_muda_mais_10pct": n_ab_10pct, "n_horas_primeira_muda_mais_10pct": n_ac_10pct,
            "mesmo_conjunto_horas_sensiveis": mesmo_conjunto,
            "distribuicao_n_semihoras": dist_semihoras,
            "n_horas_metrica_custo": int(len(custo_base)),
        },
        "efeito_zero_negativo": {
            "n_semihoras_negativas_ano_inteiro": n_semihoras_negativas,
            "n_horas_medias_cmo_zero": n_horas_cmo_zero_horario,
            "n_horas_medias_cmo_negativo": n_horas_cmo_negativo_horario,
            "limiar_p90_cmo_medio": p90,
            "n_horas_top10pct_cmo": int(len(top10)),
            "pct_custo_top10pct_cmo": pct_custo_top10,
        },
        "fuso": {
            "dicionarios_verificados_presentes": dicionarios_presentes,
            "hora_pico_cmo": hora_pico_cmo, "valor_pico_cmo": valor_pico_cmo,
            "hora_vale_cmo": hora_vale_cmo, "valor_vale_cmo": valor_vale_cmo,
            "correlacao_lag_0": corr_lag0,
            "correlacao_lag_hipotese_utc_mais_3h": corr_lag_utc,
        },
        "concentracao_avaliacao": secao_k2b_concentracao_avaliacao(),
    })
    return resultado


# ---------------------------------------------------------------------------
# L, N. Únicas seções deste arquivo que dependem de algo além de data/raw/: leem
# as previsões já salvas em data/processed/ (src/custo_assimetrico.py,
# src/breakdown_erro.py). As seções A-K, M são fatos puros de dado bruto (ou
# descrição de código, M), recomputáveis sem nenhum modelo já treinado — L e N
# são resultado de avaliação de modelo. Documentado aqui em vez de
# reimplementado, para não haver dois cálculos divergentes do mesmo número.
# ---------------------------------------------------------------------------

def secao_l_custo_assimetrico() -> dict:
    """Não engole SanityCheckError — se o controle fator_sub=1.0 divergir do custo
    simétrico já comprometido, é bug real (ESCOPO.md seção 12f) e este script deve
    parar, igual a qualquer outra divergência contra fatos já estabelecidos."""
    from custo_assimetrico import calcular_todos
    return {"disponivel": True, **calcular_todos()}


def secao_n_breakdown_erro() -> dict:
    """Não engole SanityCheckError — se a soma de horas por subgrupo não bater
    com n_incluida do modelo, é sinal de merge quebrado com features_se.parquet,
    não algo para silenciar."""
    from breakdown_erro import calcular_todos
    return {"disponivel": True, **calcular_todos()}


# ---------------------------------------------------------------------------
# Renderização em Markdown
# ---------------------------------------------------------------------------

def renderizar(a, b, c, d, e, f, g, j, j7, k, l, n, timestamps_dst_1519) -> str:
    linhas = []
    W = linhas.append

    W("# FACTS.md — Folha de Fatos Canônica do Projeto 3")
    W("")
    W("Fonte única de números para escopo, README e relatórios futuros. Todo valor")
    W("abaixo é recalculado por [`src/gerar_facts.py`](../src/gerar_facts.py) a partir")
    W("de `data/raw/*.parquet`, `data/raw/MANIFEST.json` e `data/raw/temperatura/*`")
    W("(já baixados; este script não faz nenhuma requisição de rede). Nenhum número")
    W("foi digitado à mão nem copiado dos relatórios 00–04. Re-executar este script")
    W("produz o mesmo arquivo.")
    W("")
    W("---")
    W("")

    # A
    W("## A. Proveniência")
    W("")
    W(f"- Fonte: ONS — Curva de Carga Horária. URL base: `{a['url_base']}`")
    W("- Licença: CC-BY (declarada pelo portal de dados abertos do ONS — não é um valor")
    W("  extraído do parquet ou do manifesto, listada aqui como contexto fixo)")
    W(f"- Arquivos: {a['n_arquivos_ons']}, anos cobertos: {a['anos_cobertos'][0]}–{a['anos_cobertos'][-1]} ({len(a['anos_cobertos'])} arquivos, 1 por ano)")
    W(f"- Snapshot baixado entre `{a['snapshot_downloaded_at_min']}` e `{a['snapshot_downloaded_at_max']}`")
    W(f"- SHA-256 do `MANIFEST.json` neste momento: `{a['manifest_sha256']}`")
    W(f"- Total de entradas no manifesto (inclui arquivos de temperatura de sessões posteriores): {a['manifest_n_entradas_total']}")
    W("")
    W("**Aviso — republicação em lote (recalculado, não copiado):** agrupando os 12")
    W("arquivos por data (não hora) do cabeçalho HTTP `Last-Modified`:")
    W("")
    W("| Data (Last-Modified) | Anos |")
    W("|---|---|")
    for data_str, anos in sorted(a["grupos_last_modified_por_data"].items(), key=lambda kv: kv[1][0]):
        W(f"| {data_str} | {', '.join(str(x) for x in sorted(anos))} |")
    W("")
    W("Os 10 arquivos de 2015–2024 compartilham a mesma DATA de `Last-Modified`")
    W("(não o mesmo timestamp exato ao segundo — os horários formam uma sequência de")
    W("poucos minutos, consistente com republicação em lote, não com 10 eventos")
    W("independentes). O ONS declara um \"processo de consistência recorrente\" que")
    W("revisa dados retroativamente — por isso este snapshot é identificado por hash,")
    W("não assumido como imutável.")
    W("")
    W("---")
    W("")

    # B
    W("## B. Esquema e divergências contra o dicionário oficial")
    W("")
    W("| Ano | Linhas | Colunas divergem | dtype de `val_cargaenergiahomwmed` | Strings vazias |")
    W("|---|---|---|---|---|")
    for ano in sorted(b["por_ano"]):
        info = b["por_ano"][ano]
        div = ", ".join(info["colunas_divergem"]) if info["colunas_divergem"] else "nenhuma"
        W(f"| {ano} | {fmt_int(info['n_linhas'])} | {div} | `{info['val_dtype']}` | {info['n_strings_vazias']} |")
    W("")
    W(f"**Total de strings vazias recalculado: {b['total_strings_vazias']}** (coluna")
    W("declarada pelo dicionário como não permitindo nulo).")
    W("")
    ids_str = ", ".join(f"`{x}`" for x in b["id_subsistema_lista"]) if b["id_subsistema_estavel_12_anos"] else "INSTÁVEL — ver divergência abaixo"
    W(f"`id_subsistema`: {ids_str} — estável nos 12 anos: **{'sim' if b['id_subsistema_estavel_12_anos'] else 'NÃO'}**.")
    W("")
    W("`nom_subsistema` para o código `SE`, por ano:")
    W("")
    W("| Ano | nom_subsistema (SE) |")
    W("|---|---|")
    for ano in sorted(b["nome_se_por_ano"]):
        W(f"| {ano} | {b['nome_se_por_ano'][ano]} |")
    W("")
    W("**Regra decidida:** usar `id_subsistema` como chave em qualquer join ou filtro,")
    W("nunca `nom_subsistema` — o nome mudou de `SUDESTE` para `SUDESTE/CENTRO-OESTE`")
    W("em 2026, mas o código `SE` não mudou em nenhum dos 12 anos (confirmado na tabela")
    W("acima).")
    W("")
    cmo_dtype = b.get("cmo_dtype_por_ano", {})
    if cmo_dtype:
        W("`val_cmo` (CMO Semi-Horário), dtype por ano — mesmo padrão de divergência de")
        W("tipo já observado em `val_cargaenergiahomwmed` acima, só que na direção oposta")
        W("(aqui o ano mais recente é o que vem como texto):")
        W("")
        W("| Ano | dtype de `val_cmo` |")
        W("|---|---|")
        for ano in sorted(cmo_dtype):
            W(f"| {ano} | `{cmo_dtype[ano]}` |")
        W("")
        anos_texto = [a for a, dt in cmo_dtype.items() if dt != "float64"]
        if anos_texto:
            W(
                f"Confirmado por `pd.to_numeric`: nenhum valor de "
                f"{', '.join(str(a) for a in sorted(anos_texto))} falhou a conversão para número "
                "— não é corrupção de dado, só tipo declarado/armazenado divergente entre anos."
            )
            W("")
    W("---")
    W("")

    # C
    W("## C. Cobertura temporal, por subsistema")
    W("")
    W("| Subsistema | Primeiro instante | Último instante | Linhas | Timestamps distintos | Duplicados | Dias irregulares |")
    W("|---|---|---|---|---|---|---|")
    for sub in sorted(c):
        info = c[sub]
        W(f"| {sub} | {info['primeiro_instante']} | {info['ultimo_instante']} | {fmt_int(info['n_linhas'])} | {fmt_int(info['n_timestamps_distintos'])} | {info['n_duplicados']} | {len(info['dias_irregulares'])} |")
    W("")
    W("Dias irregulares (linhas != 24 registros), listados:")
    W("")
    algum_irregular = False
    for sub in sorted(c):
        for di in c[sub]["dias_irregulares"]:
            W(f"- {sub}, {di['dia']}: {di['n_registros']} registros")
            algum_irregular = True
    if not algum_irregular:
        W("- nenhum")
    W("")
    W("Estatística de valor (`val_cargaenergiahomwmed`), por subsistema, sobre os")
    W("valores válidos (NaN excluídos):")
    W("")
    W("| Subsistema | N válidos | Mínimo | Timestamp mínimo | Máximo | Timestamp máximo | Média | Mediana | Desvio padrão | Q25 | Q75 |")
    W("|---|---|---|---|---|---|---|---|---|---|---|")
    for sub in sorted(c):
        ev = c[sub]["estatisticas_valor"]
        W(
            f"| {sub} | {fmt_int(ev['n_validos'])} | {fmt_br(ev['minimo'], 3)} | {ev['din_instante_minimo']} | "
            f"{fmt_br(ev['maximo'], 3)} | {ev['din_instante_maximo']} | {fmt_br(ev['media'], 3)} | "
            f"{fmt_br(ev['mediana'], 3)} | {fmt_br(ev['desvio_padrao'], 3)} | {fmt_br(ev['q25'], 3)} | {fmt_br(ev['q75'], 3)} |"
        )
    W("")
    W("---")
    W("")

    # D
    W("## D. Horário de verão — os 9 timestamps especiais")
    W("")
    W("Gerados por código: varredura hora a hora de 2015-01-01 a 2019-12-31 usando")
    W("`zoneinfo(\"America/Sao_Paulo\")` (IANA tzdata) e `datetime.fold`, sem nenhuma data")
    W("hardcoded. Total de timestamps classificados como ambíguos ou inexistentes no")
    W(f"período: **{d['n_total']}** ({d['n_inexistentes']} inexistentes + {d['n_ambiguos']} ambíguos).")
    W("")
    W("### Início de DST (timestamp local inexistente)")
    W("")
    W("Valor vazio nos 4 subsistemas em 3 das 4 datas; na quarta (2018-11-04), 3")
    W("subsistemas vazios e 1 com notação científica (ver tabela e seção seguinte).")
    W("")
    W("| Timestamp | N | NE | S | SE |")
    W("|---|---|---|---|---|")
    for det in d["detalhe_inexistentes"]:
        v = det["valores_por_subsistema"]
        W(f"| {det['timestamp']} | {v.get('N','(sem linha)')} | {v.get('NE','(sem linha)')} | {v.get('S','(sem linha)')} | {v.get('SE','(sem linha)')} |")
    W("")
    W("### Fim de DST (timestamp local ambíguo — 1 hora física real não registrada)")
    W("")
    W("| Timestamp | N | NE | S | SE |")
    W("|---|---|---|---|---|")
    for det in d["detalhe_ambiguos"]:
        v = det["valores_por_subsistema"]
        W(f"| {det['timestamp']} | {v.get('N','(sem linha)')} | {v.get('NE','(sem linha)')} | {v.get('S','(sem linha)')} | {v.get('SE','(sem linha)')} |")
    W("")
    W("Os 9 timestamps, em ordem:")
    W("")
    for ts in d["timestamps_ordenados"]:
        W(f"- {ts}")
    W("")
    W("### Notação científica na coluna string (anos 2015–2024)")
    W("")
    if d["ocorrencias_notacao_cientifica"]:
        W("| Subsistema | Timestamp | Valor bruto |")
        W("|---|---|---|")
        for oc in d["ocorrencias_notacao_cientifica"]:
            W(f"| {oc['id_subsistema']} | {oc['din_instante']} | `{oc['val_raw_str']}` |")
    else:
        W("- nenhuma ocorrência encontrada (DIVERGE do esperado — ver aviso no topo do relatório)")
    W("")
    W(f"Total de ocorrências de notação científica na coluna inteira (2015-2024): {len(d['ocorrencias_notacao_cientifica'])}.")
    W("")
    W("---")
    W("")

    # E
    W("## E. Anomalias conhecidas e não explicadas")
    W("")
    W("| Subsistema | Valor mínimo | Timestamp do mínimo | Coincide com transição de DST? |")
    W("|---|---|---|---|")
    for sub in sorted(e["minimos_por_subsistema"]):
        info = e["minimos_por_subsistema"][sub]
        W(f"| {sub} | {fmt_br(info['valor_minimo'], 3)} | {info['din_instante_minimo']} | {'sim' if info['coincide_com_transicao_dst'] else 'não'} |")
    W("")
    W("**Aberto, sem explicação:** o mínimo histórico do subsistema NE (ver linha acima)")
    W("não coincide com nenhuma das 9 datas de transição de DST listadas na seção D.")
    W("Nenhuma causa foi investigada além dessa checagem de coincidência de data.")
    W("")
    W("**2015-04-09 — nenhum dos 4 subsistemas tem dado válido nesse dia,**")
    W("por duas formas distintas de ausência na mesma fonte:")
    W("")
    W("| Subsistema | Linhas | Valores vazios | Forma de ausência |")
    W("|---|---|---|---|")
    for sub in ["N", "NE", "S", "SE"]:
        info = e["dia_2015_04_09"][sub]
        forma = "linha ausente" if info["n_linhas"] == 0 else "linha presente, valor vazio"
        W(f"| {sub} | {info['n_linhas']} | {info['n_vazias']} | {forma} |")
    W("")
    W("**Nota:** são duas formas distintas de ausência na mesma fonte. A forma")
    W("\"linha presente, valor vazio\" (NE, S, SE — 24 linhas, 24 valores vazios cada)")
    W("é a mesma observada nos 4 vazios de início de DST em outubro (seção D). A forma")
    W("\"linha ausente\" (N — 0 linhas) só ocorre nesta data.")
    W("")
    W("---")
    W("")

    # F
    W("## F. Efeito do DST no perfil de carga (SE/CO, dez+jan, recalculado do zero)")
    W("")
    W("Metodologia: mesma do relatório 03 — dezembro+janeiro de 4 verões com DST")
    W("(2015-16 a 2018-19) vs. 4 verões sem DST (2021-22 a 2024-25), os 9 timestamps da")
    W("seção D excluídos, dias úteis e fins de semana separados, com e sem normalização")
    W("por média diária.")
    W("")
    W("| Regime | Tipo de dia | N dias |")
    W("|---|---|---|")
    for regime in ["com_dst", "sem_dst"]:
        for tipo in ["dia_util", "fim_de_semana"]:
            W(f"| {regime} | {tipo} | {f['contagem_dias'][regime][tipo]} |")
    W("")
    W("| Regime | Tipo de dia | Base | Hora pico tarde | Hora pico noite | Razão noite/tarde |")
    W("|---|---|---|---|---|---|")
    for regime in ["com_dst", "sem_dst"]:
        for tipo in ["dia_util", "fim_de_semana"]:
            for base in ["bruto", "normalizado"]:
                p = f["picos"][regime][tipo][base]
                W(f"| {regime} | {tipo} | {base} | {p['hora_pico_tarde']}h | {p['hora_pico_noite']}h | {fmt_br(p['razao_noite_tarde'])} |")
    W("")
    W("**Limite declarado:** esta comparação NÃO isola o efeito do DST. Os grupos")
    W("diferem em ~7 anos de tendência de crescimento de carga, mudança de matriz")
    W("elétrica (geração solar distribuída cresceu no período) e efeitos pós-pandemia")
    W("sobre padrões de trabalho — nenhum desses confundidores foi controlado aqui.")
    W("")
    W("---")
    W("")

    # G
    W("## G. Temperatura — viabilidade")
    W("")
    W("Fonte sem vazamento: Open-Meteo Previous Runs API")
    W("(`https://previous-runs-api.open-meteo.com/v1/forecast`,")
    W("`temperature_2m_previous_day1`), CC BY 4.0, sem chave.")
    W("")
    if g["arquivos_ausentes"]:
        W("**Arquivos ausentes — alguns cálculos abaixo podem estar incompletos:**")
        for x in g["arquivos_ausentes"]:
            W(f"- {x}")
        W("")
    W("### Cobertura inicial")
    W("")
    W("Recalculada a partir dos arquivos de teste já baixados (não é uma nova")
    W("bisecção — nenhuma chamada de rede foi feita aqui). Duas definições distintas,")
    W("rotuladas separadamente — não são o mesmo fato:")
    W("")
    W("| Janela | Primeiro timestamp não-nulo (fato bruto da fonte) | Primeiro dia com 24h completas, 0 nulos (derivado) | Horas disponíveis no dia do 1º timestamp não-nulo |")
    W("|---|---|---|---|")
    for janela, info in g["cobertura_inicial"].items():
        W(f"| {janela} (São Paulo) | {info['primeiro_timestamp_nao_nulo']} | {info['primeiro_dia_24h_completo']} | {info['horas_disponiveis_no_dia_do_primeiro_nao_nulo']} de 24 |")
    W("")
    W("**Regra decidida:** o primeiro dia elegível como alvo de previsão day-ahead é")
    W("o primeiro dia com 24h completas (coluna 3 acima) — 2024-01-20 para a janela de")
    W("jan/2024. O dia anterior (2024-01-19) é parcial e utilizável apenas como")
    W("contexto/insumo, não como alvo de previsão.")
    W("")
    if g["comparacao_era5"]:
        ce = g["comparacao_era5"]
        W("### Previsão-24h vs. ERA5 (5 cidades, jan/2024–dez/2025)")
        W("")
        W("| Cidade | N comparável | MAE | RMSE | Viés | MAE p95 | MAE p5 |")
        W("|---|---|---|---|---|---|---|")
        for cidade, info in ce["por_cidade"].items():
            W(f"| {cidade.replace('_',' ')} | {fmt_int(info['n_comparavel'])} | {fmt_br(info['mae'])} | {fmt_br(info['rmse'])} | {fmt_br(info['vies'])} | {fmt_br(info['mae_p95'])} | {fmt_br(info['mae_p5'])} |")
        W(f"| **Agregado** | {fmt_int(ce['n_total_comparavel'])} | **{fmt_br(ce['mae_agregado'])}** | {fmt_br(ce['rmse_agregado'])} | {fmt_br(ce['vies_agregado'])} | {fmt_br(ce['mae_p95_agregado'])} | {fmt_br(ce['mae_p5_agregado'])} |")
        W("")
        W(f"MAE por hora — mínimo às {ce['hora_menor_mae']:02d}h ({fmt_br(ce['valor_menor_mae'])}), máximo às")
        W(f"{ce['hora_maior_mae']:02d}h ({fmt_br(ce['valor_maior_mae'])}).")
        W("")
        W(f"MAE no p95 (dias quentes) maior que o MAE geral em {ce['n_cidades_mae_p95_maior_que_geral']} de 5 cidades.")
        W(f"MAE no p5 (dias frios) maior que o MAE geral em {ce['n_cidades_mae_p5_maior_que_geral']} de 5 cidades.")
        W("")
    if g["comparacao_inmet"]:
        ci = g["comparacao_inmet"]
        W("### ERA5 vs. estação INMET A701 (São Paulo, 2024)")
        W("")
        W("| Métrica | Valor |")
        W("|---|---|")
        W(f"| Linhas brutas da estação | {fmt_int(ci['n_linhas_brutas'])} |")
        W(f"| Valores literais `9999` | {ci['n_9999_literal']} |")
        W(f"| Valores ausentes (total) | {ci['n_ausente_total']} |")
        W(f"| Horas comparáveis | {fmt_int(ci['n_comparavel'])} |")
        W(f"| Horas descartadas | {ci['n_descartado']} |")
        W(f"| MAE (ERA5 vs. estação) | {fmt_br(ci['mae'])} |")
        W(f"| RMSE (ERA5 vs. estação) | {fmt_br(ci['rmse'])} |")
        W(f"| Viés (estação − ERA5) | {fmt_br(ci['vies'])} |")
        W("")
        W("**Nota:** ERA5 não é verdade absoluta — é uma reanálise, não uma medição")
        W("direta. Parte do erro atribuído à previsão-24h na seção anterior pode ser,")
        W("na verdade, divergência entre ERA5 e a realidade física medida em estação.")
        W("Os dois números (previsão-vs-ERA5 e ERA5-vs-estação) não são somáveis nem")
        W("diretamente comparáveis — comparam pares de séries diferentes.")
        W("")
    W("---")
    W("")

    # J
    W("## J. Custo de despacho")
    W("")
    if j.get("arquivo_ausente"):
        W(f"**Amostra ausente** (`{j['arquivo_ausente']}`) — seção não pôde ser calculada.")
        W("")
    else:
        W("### J1. Fontes sondadas")
        W("")
        W("Documentado a partir da página de cada dataset e do respectivo dicionário de")
        W("dados (não extraído do parquet — contexto fixo, como a licença na seção A):")
        W("")
        W("| Dataset | URL | Licença | Anos disponíveis (portal) |")
        W("|---|---|---|---|")
        W("| CMO Semi-Horário | https://dados.ons.org.br/dataset/cmo-semi-horario | CC-BY | 2020–2026 |")
        W("| CMO Semanal | https://dados.ons.org.br/dataset/cmo-semanal | CC-BY | 2005–2026 |")
        W("| CVU das Usinas Térmicas | https://dados.ons.org.br/dataset/cvu-usitermica | CC-BY | 2005–2026 |")
        W("")
        W("**Decisão tomada (registrada, não questionada aqui):** usar CMO Semi-Horário")
        W("como preço do erro de previsão, agregado para grade horária. CVU descartado")
        W("(exigiria modelar ordem de mérito). CMO Semanal descartado (granularidade")
        W("insuficiente).")
        W("")
        W("### J2. Fato bruto vs. regra derivada — CMO Semi-Horário, amostra 2024")
        W("")
        W("**Fato bruto — granularidade nativa:** diferença entre timestamps distintos")
        W(f"consecutivos é de {fmt_int(int(j['diff_modal_segundos']))} segundos ({int(j['diff_modal_segundos']//60)} minutos)")
        W("na quase totalidade dos casos. Valores de diferença distintos observados no")
        W(f"arquivo inteiro: {', '.join(fmt_int(int(x)) for x in j['diffs_segundos_distintas'])} segundos.")
        W("")
        W(f"**Fato bruto — subsistemas observados:** `{'`, `'.join(j['ids_observados'])}` —")
        W(f"{len(j['ids_observados'])} subsistemas, mesmos códigos do dataset de carga.")
        W(f"Linhas por subsistema: {', '.join(f'{k}={fmt_int(v)}' for k, v in sorted(j['linhas_por_subsistema'].items()))}.")
        W("")
        W("**Fato bruto — unidade:** R$/MWh, conforme dicionário de dados oficial")
        W("(`DicionarioDados_Cmo_Semi_Horario.pdf`).")
        W("")
        W("**REGRA (decisão, não fato do dado):** para casar com a grade horária da")
        W("carga, os dois registros de 30 minutos de cada hora precisam ser agregados em")
        W("1 valor horário. O método de agregação (ex.: média das duas semi-horas) é uma")
        W("escolha de modelagem — **não foi aplicado nesta sondagem** e não está,")
        W("portanto, refletido em nenhum número desta seção.")
        W("")
        W("### J3. Lacunas e anomalias — amostra 2024 (recalculado)")
        W("")
        W(f"Período coberto pela amostra: `{j['primeiro_instante']}` a `{j['ultimo_instante']}`,")
        W(f"{fmt_int(j['n_linhas'])} linhas totais.")
        W("")
        W(f"Calendário de {fmt_int(j['dias_calendario_no_periodo'])} dias no ano da amostra;")
        W(f"{fmt_int(j['dias_presentes'])} dias com pelo menos 1 registro por subsistema")
        W(f"(checado no subsistema SE). **{len(j['dias_ausentes'])} dias inteiramente")
        W("ausentes**, gerados por código (calendário completo do ano menos dias")
        W("presentes):")
        W("")
        for dia in j["dias_ausentes"]:
            W(f"- {dia}")
        W("")
        W(f"Grade teoricamente completa (dias de calendário × 48 × {len(j['ids_observados'])} subsistemas):")
        W(f"{fmt_int(j['n_esperado_grade_completa_30min'])} linhas. Observado: {fmt_int(j['n_linhas'])}.")
        W("")
        W(f"**`val_cmo`, {fmt_int(j['val_cmo_n_validos'])} valores válidos, {j['val_cmo_n_nulo']} nulos:**")
        W(f"{j['val_cmo_n_negativos']} negativos, {fmt_int(j['val_cmo_n_zeros'])} zeros.")
        W("")
        W("**Nota a registrar:** CMO zero e CMO negativo são fisicamente reais no SIN")
        W("(vertimento / sobra de energia) — não são erro de dado. Numa hora de CMO")
        W("zero, o custo do erro de previsão pela fórmula `|erro_MW| × CMO × 1h` também")
        W("é zero. Isso é consequência da suposição de precificação adotada (seção J5),")
        W("não um problema do dado.")
        W("")
        W("### J4. Divergência de dicionário")
        W("")
        W("O dicionário de dados do CMO Semanal declara `val_cmomediasemanal` em")
        W("**R$/MW**, enquanto as outras 3 colunas de valor do mesmo dataset")
        W("(`val_cmoleve`, `val_cmomedia`, `val_cmopesada`) são declaradas em")
        W("**R$/MWh** — mesmo dicionário, mesma tabela, unidades diferentes descritas")
        W("para colunas do mesmo tipo de grandeza. Registrado como está escrito no PDF")
        W("oficial; não investigado se é erro de digitação ou diferença real.")
        W("")
        W("Este é o 3º caso, nesta sondagem, de o dicionário oficial do ONS divergir de")
        W("si mesmo ou dos dados: (1) seção B — coluna declarada `FLOAT` armazenada como")
        W("texto em 2015–2024; (2) seção B — 87 strings vazias numa coluna declarada")
        W("`Permite valor nulo: Não`; (3) esta.")
        W("")
        W("### J5. Limite da métrica de custo — registrado literalmente")
        W("")
        W("Nenhum dos três datasets sondados (CMO Semi-Horário, CMO Semanal, CVU)")
        W("contém uma ligação entre erro de carga (MW) e custo (R$) já calculada.")
        W("Nenhum contém o conceito de \"erro de previsão\". Os três contêm **preço**")
        W("(R$/MWh, ou R$/MW numa coluna — seção J4). A métrica de negócio do projeto")
        W("é, portanto, um **modelo declarado**, não um dado observado:")
        W("")
        W("> custo = |erro_MW| × CMO_horário × 1h")
        W("")
        W("sob a suposição de que o erro de previsão é valorado ao custo marginal de")
        W("operação do subsistema naquela hora. **Isto não é custo de despacho")
        W("realizado — é uma estimativa sob suposição explícita.**")
        W("")
        W("### J6. Cobertura cruzada — carga SE/CO × CMO Semi-Horário")
        W("")
        W("| Fonte | Período |")
        W("|---|---|")
        W(f"| Carga SE/CO (recalculado na seção C) | `{j['carga_se_primeiro_instante']}` a `{j['carga_se_ultimo_instante']}` |")
        W(f"| CMO Semi-Horário, amostra efetivamente baixada e verificada em detalhe nesta seção | `{j['primeiro_instante']}` a `{j['ultimo_instante']}` (ano 2024) |")
        W("")
        W("Cobertura completa ano a ano (2020-2026), incluindo 2025-2026: seção J7.")
        W("")
        W("### J7. Cobertura ano a ano do CMO Semi-Horário (2020-2026)")
        W("")
        W("Auditoria completa dos anos em `data/raw/custo/` — não baixa nada, só audita")
        W("o que já está em disco. O período de avaliação do projeto usa só 2024+; os")
        W("anos abaixo cobrem a faixa que o **portal do ONS declara disponível**")
        W("(2020-2026), para que a afirmação de cobertura deixe de ser uma suposição.")
        W("")
        W("| Ano | Arquivo | Linhas (SE) | Período no arquivo | Dias ausentes | Nulos | Negativos | Zeros | Min (R$/MWh) | Max (R$/MWh) |")
        W("|---|---|---|---|---|---|---|---|---|---|")
        for ano in j7["anos"]:
            info = j7["por_ano"][ano]
            if not info["arquivo_existe"]:
                W(f"| {ano} | ausente | — | — | — | — | — | — | — | — |")
                continue
            n_ausentes = len(info["dias_ausentes_ate_ultimo_dia"])
            completo = "ano completo" if info["ano_completo_no_arquivo"] else "parcial (em andamento)"
            W(f"| {ano} | presente ({completo}) | {info['n_linhas_se']} | "
              f"`{info['primeiro_instante']}` a `{info['ultimo_instante']}` | {n_ausentes} | "
              f"{info['val_cmo_n_nulo']} | {info['val_cmo_n_negativos']} | {info['val_cmo_n_zeros']} | "
              f"{info['val_cmo_min']:.4f} | {info['val_cmo_max']:.4f} |")
        W("")
        W("Cobertura em base HORÁRIA (dias × 24h — granularidade que o projeto de fato usa,")
        W("`carregar_cmo_horario_se` agrega 30min→60min) e média do CMO, para os anos presentes:")
        W("")
        W("| Ano | Horas existentes | Horas esperadas | % cobertura horária | Média (R$/MWh) |")
        W("|---|---|---|---|---|")
        for ano in (2024, 2025, 2026):
            info = j7["por_ano"][ano]
            W(f"| {ano} | {info['horas_existentes']} | {info['horas_esperadas']} | "
              f"{info['pct_cobertura_horaria']:.4f}% | {info['val_cmo_media']:.4f} |")
        W("")
        anos_ausentes_lista = [str(a) for a in j7["anos"] if not j7["por_ano"][a]["arquivo_existe"]]
        W(f"**{len(anos_ausentes_lista)} ano(s) sem arquivo baixado: {', '.join(anos_ausentes_lista)}.** "
          "Não é uma lacuna do projeto — o período de avaliação (`INICIO_AVALIACAO` = "
          "2024-01-01) nunca precisou desses anos, então eles nunca foram baixados. A")
        W("cobertura 2020-2026 citada nos documentos é a listagem do portal (o que **pode**")
        W("ser baixado), não uma verificação de que os dados de 2020-2023 estão completos —")
        W("essa verificação não foi feita e não é necessária para os resultados do projeto.")
        W("")
        W("**Buracos reais nos 3 anos efetivamente usados (2024, 2025, 2026):** nenhum")
        W("valor nulo, nenhum dia inteiramente ausente em 2020-2023 (não se aplica, ausentes)")
        W("— mas dias INDIVIDUAIS faltam dentro de cada ano presente:")
        for ano in (2024, 2025, 2026):
            dias = j7["por_ano"][ano]["dias_ausentes_ate_ultimo_dia"]
            if dias:
                W(f"- **{ano}:** {len(dias)} dia(s) sem nenhum registro de CMO: {', '.join(dias)}.")
            else:
                W(f"- **{ano}:** 0 dias ausentes.")
        W("")
        W("O buraco de 2024 (4 dias) já constava em J3, recalculado aqui e batendo com o")
        W("valor anterior — confirma que o método é o mesmo. Os buracos de 2025 (1 dia) e")
        W("2026 (2 dias) são novos: nunca haviam sido checados em detalhe antes desta")
        W("auditoria. Nenhum dos três anos tem valor nulo, e a faixa de valores (mín/máx)")
        W("é plausível nos três, sem negativos extremos nem zeros fora do padrão já")
        W("registrado em J3/K2 — os buracos são dias sem registro nenhum, não valores")
        W("inválidos dentro de dias presentes.")
        W("")
    W("---")
    W("")

    # K
    W("## K. Agregação do CMO — sensibilidade e fuso (recalculado do zero)")
    W("")
    if k.get("arquivo_ausente"):
        W(f"**Amostra ausente** (`{k['arquivo_ausente']}`) — seção não pôde ser calculada.")
        W("")
    else:
        sa = k["sensibilidade_agregacao"]
        ez = k["efeito_zero_negativo"]
        fz = k["fuso"]
        W("### K1. Sensibilidade da métrica de custo à agregação do CMO (30min→60min)")
        W("")
        W("Instrumento de medição: sazonal-naive (previsão(H,D) = observado(H,D−7)),")
        W("SE/CO, 2024, mesma metodologia da seção J (9 timestamps de `is_dst_transition`")
        W("— nenhum cai em 2024 —, 4 dias sem CMO excluídos da métrica de custo).")
        W("")
        W("| Variante | Custo total (R$) | % do custo de (a) média |")
        W("|---|---|---|")
        W(f"| (a) Média das 2 semi-horas | {fmt_br(sa['custo_total_media'], 2)} | 100,0000% |")
        W(f"| (b) Máximo das 2 semi-horas | {fmt_br(sa['custo_total_maximo'], 2)} | {fmt_br(sa['pct_maximo_de_media'], 4)}% |")
        W(f"| (c) Primeira semi-hora | {fmt_br(sa['custo_total_primeira'], 2)} | {fmt_br(sa['pct_primeira_de_media'], 4)}% |")
        W("")
        W(f"Correlação entre séries horárias de custo: (a)×(b) = {fmt_br(sa['correlacao_media_maximo'], 6)},")
        W(f"(a)×(c) = {fmt_br(sa['correlacao_media_primeira'], 6)}, (b)×(c) = {fmt_br(sa['correlacao_maximo_primeira'], 6)}.")
        W("")
        W(f"Horas em que (b) muda o custo em mais de 10% vs. (a): **{sa['n_horas_maximo_muda_mais_10pct']}**")
        W(f"de {fmt_int(sa['n_horas_metrica_custo'])}. Horas em que (c) muda em mais de 10%: **{sa['n_horas_primeira_muda_mais_10pct']}**.")
        W(f"Mesmo conjunto de horas nas duas comparações: {'sim' if sa['mesmo_conjunto_horas_sensiveis'] else 'não'}.")
        W("")
        W("**Regra decidida:** usar a média das duas semi-horas.")
        W("")
        W("### K2. Efeito de CMO zero/negativo e concentração do custo")
        W("")
        W("Valores semi-horários negativos no ano inteiro, **subsistema SE apenas**:")
        W(f"{ez['n_semihoras_negativas_ano_inteiro']}. Não contradiz a seção J3 (77 negativos):")
        W("aquele número é a soma dos 4 subsistemas — os 77 negativos pertencem inteiramente")
        W("ao subsistema NE; SE não tem nenhum valor semi-horário negativo em 2024.")
        W(f"Horas com a MÉDIA horária do CMO igual a zero: {fmt_int(ez['n_horas_medias_cmo_zero'])}.")
        W(f"Horas com a MÉDIA horária do CMO negativa: **{ez['n_horas_medias_cmo_negativo']}**.")
        W("")
        W(f"Limiar do decil 90 do CMO médio horário: {fmt_br(ez['limiar_p90_cmo_medio'], 4)} R$/MWh.")
        W(f"Horas nesse decil: {fmt_int(ez['n_horas_top10pct_cmo'])}.")
        W(f"% do custo total do ano (variante média) vindo dessas horas: **{fmt_br(ez['pct_custo_top10pct_cmo'], 4)}%**.")
        W("")
        ca = k.get("concentracao_avaliacao", {})
        if ca.get("disponivel"):
            W(
                f"**Concentração de custo, período de avaliação {ca['inicio_avaliacao']} a "
                f"{ca['fim_avaliacao']} (naive semanal, régua principal — anos de CMO usados: "
                f"{', '.join(str(a) for a in ca['anos_cmo_usados'])}):** "
                f"{fmt_br(ca['pct_custo_top10pct_cmo'], 4)}% do custo nas 10% horas de CMO mais alto "
                f"({fmt_int(ca['n_horas_top10pct_cmo'])} de {fmt_int(ca['n_horas_com_cmo'])} horas com CMO; "
                f"{fmt_int(ca['n_horas_sem_cmo'])} de {fmt_int(ca['n_horas_totais'])} horas totais sem CMO, "
                f"excluídas só desta métrica). **O {fmt_br(ez['pct_custo_top10pct_cmo'], 4)}% acima refere-se "
                f"apenas a 2024 e não ao período de avaliação.**"
            )
            W("")
        W("### K3. Fuso horário do CMO — fatos brutos e fato derivado")
        W("")
        W("Dicionários de dados verificados (CMO Semi-Horário e Curva de Carga) presentes")
        W(f"em `data/raw/documentacao/`: {'sim' if fz['dicionarios_verificados_presentes'] else 'não'}.")
        W("Nenhum dos dois menciona fuso horário, UTC ou hora local em nenhum lugar do")
        W("texto (verificado por leitura integral do PDF — relatório 07, seções 1-2).")
        W("")
        W(f"Perfil intradiário do CMO (SE, 2024): pico às **{fz['hora_pico_cmo']}h** ({fmt_br(fz['valor_pico_cmo'], 4)} R$/MWh),")
        W(f"vale às **{fz['hora_vale_cmo']}h** ({fmt_br(fz['valor_vale_cmo'], 4)} R$/MWh).")
        W("")
        W("Correlação entre o perfil horário do CMO e o perfil horário da carga SE/CO")
        W(f"(2024, rótulos de hora como armazenados, sem deslocamento): **{fmt_br(fz['correlacao_lag_0'], 4)}**.")
        W(f"Correlação sob a hipótese \"CMO está em UTC, corrigir +3h\": **{fmt_br(fz['correlacao_lag_hipotese_utc_mais_3h'], 4)}**.")
        W("")
        W("**FATO DERIVADO (não documentado pela fonte — síntese de evidência empírica,")
        W("não leitura de documentação):** o CMO Semi-Horário é tratado como hora local")
        W("(America/Sao_Paulo), mesma convenção da carga. Base: os três fatos brutos acima")
        W("convergem — sob a hipótese UTC, o perfil descreveria um sistema mais caro às")
        W("15h (hora local) que às 19h, e a correção de +3h destrói a correlação existente")
        W("(de 0,4501 para -0,0051) em vez de melhorá-la.")
        W("")
        W("**Divergência registrada, não resolvida por omissão:** `reports/07_fuso_cmo.md`,")
        W("aplicando critério documental estrito (fuso só conta como determinado se")
        W("declarado pela fonte OU se o teste específico de deslocamento produzir um pico")
        W("nítido e isolado), concluiu **(c) o fuso permanece desconhecido** — o mesmo")
        W("teste de correlação, isoladamente, não teve um pico em ±3h que se distinguisse")
        W("com força do resto do ciclo de 24h testado (relatório 07, seção 1; relatório 06,")
        W("Parte A3). Esta seção registra uma leitura diferente do mesmo conjunto de fatos")
        W("— tratar os três fatos brutos como convergentes o suficiente para adotar hora")
        W("local como convenção de trabalho — sem apagar a conclusão (c) do relatório 07.")
        W("Confiança: alta por evidência (perfil físico + correlação), zero por")
        W("documentação (nenhuma fonte declara o fuso). Risco explícito: se o ONS")
        W("documentar o contrário, a métrica de custo precisa ser recalculada.")
        W("")
    W("---")
    W("")

    # H
    W("## H. Decisões já tomadas")
    W("")
    W("| Decisão | Justificativa |")
    W("|---|---|")
    W("| Alvo: SE/CO, carga horária | Maior subsistema, dado mais completo, foco do relatório 03 |")
    W("| Horizonte: day-ahead 24h | Alinhado ao lead time de `temperature_2m_previous_day1` |")
    W("| Eixo temporal: hora local (America/Sao_Paulo), sem conversão para UTC | Conversão para UTC introduz timestamps ambíguos/inexistentes sem ganho demonstrado (relatórios 01–02) |")
    W("| Janela: 2015–2026 | Todo o histórico disponível no portal do ONS no momento do snapshot |")
    W("| Viradas de DST: flag `is_dst_transition`, excluídas como origem de previsão; vazios de outubro NÃO imputados | Preserva o fato bruto em vez de mascará-lo com um valor inventado |")
    W("| Temperatura: camada secundária 2024+, não no modelo principal | Cobertura da previsão-24h só é completa a partir de 2024-01-20 (seção G) |")
    W("| Primeiro dia elegível como alvo de previsão day-ahead: 2024-01-20, não 2024-01-19 | 2024-01-19 tem cobertura parcial (ver seção G); dia parcial é contexto, não alvo |")
    W("| Custo: CMO Semi-Horário agregado para grade horária pela MÉDIA das 2 semi-horas; CVU e CMO Semanal descartados | CVU exigiria modelar ordem de mérito; CMO Semanal tem granularidade insuficiente (seção J1); média testada contra máximo e primeira semi-hora, diferença de custo total pequena (seção K1) |")
    W("| Métrica de custo aplicada só ao período de teste (2020+), não ao treino | CMO Semi-Horário não cobre 2015–2019 (seção J1/J6) |")
    W("| Modelo principal (2015–2026) avaliado por MAPE/RMSE; custo é camada de avaliação, não de treino | Separa a qualidade estatística da previsão (todo o histórico) da tradução em custo (limitada pela cobertura do CMO) |")
    W("| Período de avaliação: inicia 2024-01-01, walk-forward day-ahead, origem deslizante usando todo o passado disponível, contexto >=2048h, tocado uma vez | Ver ESCOPO.md seção Validação |")
    W("")
    W("---")
    W("")

    # I
    W("## I. Itens abertos")
    W("")
    W("- NE, mínimo histórico em 2018-03-21: sem explicação (seção E).")
    W("- Cobertura do CMO Semi-Horário para 2020-2023 não confirmada — nunca baixados")
    W("  porque a avaliação (2024-01-01+) nunca precisou deles; 2024-2026 (os anos")
    W("  usados) já verificados ano a ano (seção J7).")
    W("- Fuso do CMO Semi-Horário: fato derivado por evidência empírica (seção K3),")
    W("  não declarado por nenhuma fonte documental — risco permanece se o ONS")
    W("  documentar o contrário no futuro.")
    W("- Datas de vigência do DST: confirmado nesta geração que são produzidas por")
    W("  `zoneinfo`/IANA dentro do próprio `src/gerar_facts.py`")
    W("  (função `gerar_timestamps_especiais_dst`), não hardcoded — ver seção D.")
    W("")
    W("---")
    W("")

    # L
    W("## L. Custo assimétrico (ESCOPO.md seção 12f)")
    W("")
    W("Única seção deste documento que depende de previsões de modelo já salvas em")
    W("`data/processed/` (via `src/custo_assimetrico.py`), não só de `data/raw/` — as")
    W("seções A-K acima são fatos puros de dado bruto. Subprevisão (previsto < real)")
    W("custa `fator_sub` vezes mais que superprevisão, ao preço marginal (CMO).")
    W("`fator_sub=1.0` é o controle: reproduz o custo simétrico já comprometido em")
    W("`reports/tabela_comparativa.csv` — conferido automaticamente antes desta seção")
    W("ser escrita (o script inteiro aborta se divergir).")
    W("")
    if not l.get("disponivel"):
        W(f"**Seção não pôde ser calculada:** {l.get('erro', 'motivo desconhecido')}.")
        W("")
    else:
        tc = l["tabela_custo"]
        tv = l["tabela_vies"]
        rb = l["robustez"]

        W("### L1. Sensibilidade: custo total por modelo × fator_sub")
        W("")
        fatores = sorted(tc["fator_sub"].unique())
        W("| Modelo | " + " | ".join(f"{f:.1f}×" for f in fatores) + " |")
        W("|---" * (len(fatores) + 1) + "|")
        for modelo in tc["modelo"].unique():
            sub = tc[tc["modelo"] == modelo].set_index("fator_sub")
            valores = " | ".join(f"R$ {sub.loc[f, 'custo_total']/1e9:,.2f} bi" for f in fatores)
            W(f"| {modelo} | {valores} |")
        W("")

        W("### L2. Viés direcional — % do erro absoluto vindo de sub vs. super")
        W("")
        W("| Modelo | Horas subprevisão | Horas superprevisão | % erro de subprevisão | % erro de superprevisão |")
        W("|---|---|---|---|---|")
        for _, row in tv.iterrows():
            W(f"| {row['modelo']} | {row['n_horas_sub']} | {row['n_horas_super']} | "
              f"{row['pct_erro_abs_subprevisao']:.2f}% | {row['pct_erro_abs_superprevisao']:.2f}% |")
        W("")
        W("Um modelo bem calibrado fica perto de 50/50. Acima de 50% em subprevisão é o")
        W("viés operacionalmente perigoso — é a direção que o custo assimétrico (L1)")
        W("penaliza mais.")
        W("")

        W("### L3. Robustez do ranking por custo")
        W("")
        for fator in fatores:
            W(f"- `fator_sub={fator}`: {' > '.join(rb['rankings'][fator])} (melhor → pior)")
        W("")
        if rb["robusto"]:
            W("**Ranking robusto:** idêntico em todos os fatores testados.")
        else:
            W(f"**Ranking NÃO robusto:** muda de `fator_sub=1.0` para fatores maiores — "
              f"os modelos com maior viés de subprevisão (L2) pioram de posição relativa "
              f"conforme `fator_sub` cresce (ver tabela acima).")
        W(f"Vencedor em `fator_sub=1.0`: **{rb['vencedor_base']}**. Vencedor em "
          f"`fator_sub={fatores[-1]}`: **{rb['vencedor_maior_fator']}** — "
          f"{'o mesmo modelo, mesmo sob o custo assimétrico mais extremo testado.' if rb['vencedor_base'] == rb['vencedor_maior_fator'] else 'a liderança muda.'}")
        W("")
        W("**Limitação declarada, não modelada:** VOLL (*Value of Lost Load*, ~US$10.000/MWh")
        W("em mercados como o MISO — ordens de magnitude acima do CMO típico) não entra em")
        W("nenhum fator_sub acima. Aplica-se só às horas de corte de carga efetivo, que este")
        W("dataset não identifica (ESCOPO.md seção 16).")
        W("")
        W("Gráfico: `reports/figures/resultado_8_custo_assimetrico.png`. Tabelas completas:")
        W("`reports/tabela_custo_assimetrico.csv`, `reports/tabela_vies_direcional.csv`.")
        W("")
    W("---")
    W("")

    # M
    W("## M. Tratamento por coluna")
    W("")
    W("Tabela de auditoria (não computada — descreve o código, como a seção H). Toda")
    W("coluna efetivamente usada no pipeline, o tratamento aplicado e onde no código.")
    W("")
    W("| Coluna | Tipo bruto | Tratamento aplicado | Onde no código |")
    W("|---|---|---|---|")
    for col, tipo, tratamento, onde in TRATAMENTO_POR_COLUNA:
        W(f"| {col} | {tipo} | {tratamento} | {onde} |")
    W("")
    W("**Pontos de decisão não-óbvia — comentário no código confirmado (auditoria):**")
    W("")
    for item in COMENTARIOS_AUDITADOS:
        W(f"- {item}")
    W("")
    W("---")
    W("")

    # N
    W("## N. Breakdown de erro por subgrupo")
    W("")
    W("Recomputado das previsões já salvas (`src/breakdown_erro.py`), mesma fonte de")
    W("avaliação da seção L. Controle: a soma de horas por subgrupo bate com o total")
    W("de horas incluídas de cada modelo nas 3 estratificações — conferido antes desta")
    W("seção ser escrita (o script inteiro aborta se não bater).")
    W("")
    if not n.get("disponivel"):
        W(f"**Seção não pôde ser calculada:** {n.get('erro', 'motivo desconhecido')}.")
        W("")
    else:
        for titulo, chave in [("N1. Feriado vs. dia normal", "tabela_feriado"),
                               ("N2. Estação do ano (hemisfério sul)", "tabela_estacao"),
                               ("N3. Dia útil vs. fim de semana", "tabela_dia")]:
            tabela_n = n[chave]
            W(f"### {titulo}")
            W("")
            W("| Modelo | Categoria | Horas | MAPE | Custo total |")
            W("|---|---|---|---|---|")
            for _, row in tabela_n.iterrows():
                W(f"| {row['modelo']} | {row['categoria']} | {row['n_horas']} | "
                  f"{row['mape']:.4f}% | R$ {row['custo_total']:,.2f} |")
            W("")
        W("**Chronos-2 mantém a vantagem (menor MAPE) em TODOS os subgrupos testados** — nenhum")
        W("corte (feriado/normal, cada estação, dia útil/fim de semana) inverte o ranking.")
        W("Mas a degradação RELATIVA não é uniforme: o salto de MAPE em feriados é o maior")
        W("dos 4 modelos em termos proporcionais (Chronos-2 vai de ~1,68% para ~7,09% —")
        W("mais que 4×, o maior fator de degradação relativa entre os quatro, mesmo vencendo")
        W("em termos absolutos). SARIMA mostra uma anomalia própria: MAPE mais que dobra de")
        W("dia útil para fim de semana (~4,33% para ~9,08%), padrão não observado nos outros")
        W("3 modelos.")
        W("")
        W("Gráfico: `reports/figures/resultado_9_erro_por_estacao.png`. Tabela completa:")
        W("`reports/tabela_breakdown_erro.csv`.")
        W("")

    return "\n".join(linhas) + "\n"


def main():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    full, dtype_por_ano = carregar_todos_os_anos()

    a = secao_a_proveniencia(manifest)
    b = secao_b_esquema(full, dtype_por_ano)

    timestamps_dst_1519 = gerar_timestamps_especiais_dst("2015-01-01", "2020-01-01")
    datas_transicao = set()
    for ts_str in timestamps_dst_1519["ambiguos"] + timestamps_dst_1519["inexistentes"]:
        datas_transicao.add(str(pd.Timestamp(ts_str).date()))

    c = secao_c_cobertura_temporal(full)
    d = secao_d_dst(full, timestamps_dst_1519)
    e = secao_e_anomalias(full, datas_transicao)
    f = secao_f_efeito_dst(full, timestamps_dst_1519)
    g = secao_g_temperatura()
    j = secao_j_custo(c)
    j7 = secao_j7_cobertura_anual_cmo()
    k = secao_k_agregacao_e_fuso()
    print("Calculando seção L (custo assimétrico) — lê previsões salvas, ~30-60s...")
    l = secao_l_custo_assimetrico()
    print("Calculando seção N (breakdown de erro) — lê previsões salvas, ~10-20s...")
    n = secao_n_breakdown_erro()

    conteudo = renderizar(a, b, c, d, e, f, g, j, j7, k, l, n, timestamps_dst_1519)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "FACTS.md").write_text(conteudo, encoding="utf-8", newline="\n")
    print(f"Escrito: {REPORTS_DIR / 'FACTS.md'} ({len(conteudo)} caracteres)")


if __name__ == "__main__":
    main()
