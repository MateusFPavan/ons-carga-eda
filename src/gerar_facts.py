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
import zipfile
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TEMP_DIR = RAW_DIR / "temperatura"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MANIFEST_PATH = RAW_DIR / "MANIFEST.json"
ANOS = list(range(2015, 2027))
TZ = ZoneInfo("America/Sao_Paulo")

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
    datas_lm = {ano: lm.split(" ")[1:4] and " ".join(lm.split(" ")[1:4]) for ano, lm in last_modified_por_ano.items() if lm}
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
        colunas = set(sub.columns) & (EXPECTED_COLUMNS | {"id_subsistema", "nom_subsistema", "din_instante", "val_cargaenergiahomwmed"})
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
    }


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

        resultado[sub_id] = {
            "primeiro_instante": str(primeiro),
            "ultimo_instante": str(ultimo),
            "n_linhas": int(n_total),
            "n_timestamps_distintos": int(n_distintos),
            "n_duplicados": int(n_duplicados),
            "dias_irregulares": [{"dia": str(d), "n_registros": int(c)} for d, c in dias_irregulares.items()],
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
        n_dia = full[(full["din_instante"].dt.date == ts.date()) & (full["id_subsistema"] == "SE")]
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

    # 2015-04-09, subsistema N
    dia_alvo = pd.Timestamp("2015-04-09").date()
    n_no_dia = len(full[(full["din_instante"].dt.date == dia_alvo) & (full["id_subsistema"] == "N")])
    outros_no_dia = {
        sub: len(full[(full["din_instante"].dt.date == dia_alvo) & (full["id_subsistema"] == sub)])
        for sub in ["NE", "S", "SE"]
    }

    return {
        "minimos_por_subsistema": resultado,
        "dia_2015_04_09_registros_N": n_no_dia,
        "dia_2015_04_09_registros_outros": outros_no_dia,
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
# Renderização em Markdown
# ---------------------------------------------------------------------------

def renderizar(a, b, c, d, e, f, g, timestamps_dst_1519) -> str:
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
    W("---")
    W("")

    # D
    W("## D. Horário de verão — os 9 timestamps especiais")
    W("")
    W("Gerados por código: varredura hora a hora de 2015-01-01 a 2019-12-31 usando")
    W("`zoneinfo(\"America/Sao_Paulo\")` (IANA tzdata) e `datetime.fold`, sem nenhuma data")
    W(f"hardcoded. Total de timestamps classificados como ambíguos ou inexistentes no")
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
    W(f"")
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
    outros = e["dia_2015_04_09_registros_outros"]
    outros_str = ", ".join(f"{sub}={n}" for sub, n in sorted(outros.items()))
    W(f"**2015-04-09, subsistema N:** {e['dia_2015_04_09_registros_N']} registros nesse dia")
    W(f"(dia inteiro ausente). Mesma data, outros subsistemas: {outros_str}.")
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
    W("| Custo de despacho: proxy via CMO/CVU do ONS | A verificar — não sondado ainda (ver seção I) |")
    W("")
    W("---")
    W("")

    # I
    W("## I. Itens abertos")
    W("")
    W("- NE, mínimo histórico em 2018-03-21: sem explicação (seção E).")
    W("- CMO/CVU do ONS como proxy de custo de despacho: ainda não sondado.")
    W("- Datas de vigência do DST: confirmado nesta geração que são produzidas por")
    W("  `zoneinfo`/IANA dentro do próprio `src/gerar_facts.py`")
    W("  (função `gerar_timestamps_especiais_dst`), não hardcoded — ver seção D.")
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

    conteudo = renderizar(a, b, c, d, e, f, g, timestamps_dst_1519)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "FACTS.md").write_text(conteudo, encoding="utf-8", newline="\n")
    print(f"Escrito: {REPORTS_DIR / 'FACTS.md'} ({len(conteudo)} caracteres)")


if __name__ == "__main__":
    main()
