"""Verificação independente: relê reports/FACTS.md e confere cada número tabular
contra os dados brutos, recalculando de forma independente de src/gerar_facts.py
(consultas diretas, sem reusar as funções daquele script). Reporta qualquer
divergência — não corrige nada.
"""
import json
import re
import zipfile
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

import numpy as np
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TEMP_DIR = RAW_DIR / "temperatura"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
FACTS_PATH = REPORTS_DIR / "FACTS.md"
ANOS = list(range(2015, 2027))

erros = []


def checar(descricao, esperado, obtido):
    ok = str(esperado) == str(obtido)
    status = "OK" if ok else "DIVERGE"
    print(f"[{status}] {descricao}: facts={esperado!r} recalculo_independente={obtido!r}")
    if not ok:
        erros.append((descricao, esperado, obtido))
    return ok


def main():
    texto = FACTS_PATH.read_text(encoding="utf-8")

    print("=== Carregando dados brutos (consulta independente por ano) ===")
    frames = []
    dtype_por_ano = {}
    for ano in ANOS:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        df = pd.read_parquet(fpath)
        dtype_por_ano[ano] = str(df["val_cargaenergiahomwmed"].dtype)
        df["ano_arquivo"] = ano
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    full["id_subsistema"] = full["id_subsistema"].astype(str)
    full["val_raw_str"] = full["val_cargaenergiahomwmed"].astype(str)
    full["val_num"] = pd.to_numeric(full["val_cargaenergiahomwmed"], errors="coerce")

    print("\n=== B. dtype e strings vazias por ano ===")
    for ano in ANOS:
        sub = full[full["ano_arquivo"] == ano]
        dtype_esperado_na_linha = f"| {ano} |"
        linha = next((l for l in texto.splitlines() if l.startswith(dtype_esperado_na_linha)), None)
        if linha is None:
            print(f"[FALTA] linha da tabela B para o ano {ano} não encontrada no FACTS.md")
            erros.append((f"linha B ano {ano}", "presente", "ausente"))
            continue
        dtype_no_facts = linha.split("`")[1]
        checar(f"dtype {ano}", dtype_por_ano[ano], dtype_no_facts)
        n_vazias_no_facts = int(linha.rstrip("|").rsplit("|", 1)[-1].strip())
        n_vazias_real = int((sub["val_cargaenergiahomwmed"].astype(str).str.strip() == "").sum())
        checar(f"strings vazias {ano}", n_vazias_real, n_vazias_no_facts)

    total_vazias_real = int((full["val_raw_str"].str.strip() == "").sum())
    m = re.search(r"Total de strings vazias recalculado: (\d+)", texto)
    checar("total strings vazias", total_vazias_real, int(m.group(1)) if m else None)

    print("\n=== C. cobertura temporal ===")
    for sub_id, g in full.groupby("id_subsistema"):
        ts = g["din_instante"].sort_values()
        n_total = len(g)
        n_distintos = ts.nunique()
        n_dup = n_total - n_distintos
        linha = next((l for l in texto.splitlines() if l.startswith(f"| {sub_id} |")), None)
        if linha and "din_instante" not in linha:
            campos = [c.strip() for c in linha.strip("|").split("|")]
            checar(f"{sub_id} n_linhas", f"{n_total:,}".replace(",", "."), campos[3])
            checar(f"{sub_id} duplicados", n_dup, int(campos[5]))

    print("\n=== D. timestamps DST (recomputados via zoneinfo, independente) ===")
    tz = ZoneInfo("America/Sao_Paulo")

    def classificar(ts):
        d0 = datetime(ts.year, ts.month, ts.day, ts.hour, tzinfo=tz, fold=0)
        d1 = datetime(ts.year, ts.month, ts.day, ts.hour, tzinfo=tz, fold=1)
        u0, u1 = d0.astimezone(timezone.utc), d1.astimezone(timezone.utc)
        if u0 == u1:
            return "ok"
        back0 = u0.astimezone(tz)
        return "inexistente" if (back0.hour, back0.minute) != (ts.hour, ts.minute) else "ambiguo"

    horas = pd.date_range("2015-01-01", "2020-01-01", freq="h", inclusive="left")
    especiais = [str(h) for h in horas if classificar(h) != "ok"]
    m = re.search(r"Total de timestamps classificados como ambíguos ou inexistentes no\nperíodo: \*\*(\d+)\*\*", texto)
    checar("total timestamps DST especiais", len(especiais), int(m.group(1)) if m else None)

    print("\n=== E. mínimos por subsistema ===")
    for sub_id, g in full.groupby("id_subsistema"):
        valido = g.dropna(subset=["val_num"])
        idx_min = valido["val_num"].idxmin()
        row = valido.loc[idx_min]
        linha = next((l for l in texto.splitlines() if l.startswith(f"| {sub_id} |") and "coincide" not in l.lower() and "timestamp do m" not in l.lower() and len(l.split("|")) == 6), None)
        # localizar na tabela de minimos (colunas: subsistema, valor, timestamp, coincide)
        for l in texto.splitlines():
            if l.startswith(f"| {sub_id} |"):
                campos = [c.strip() for c in l.strip("|").split("|")]
                if len(campos) == 4 and ":" in campos[2]:
                    checar(f"{sub_id} timestamp minimo", str(row["din_instante"]), campos[2])
                    break

    print("\n=== G. temperatura (recomputo independente a partir dos JSON já baixados) ===")
    for cidade in ["Sao_Paulo", "Rio_de_Janeiro", "Belo_Horizonte", "Brasilia", "Goiania"]:
        era5_path = TEMP_DIR / f"era5_temperature_2m_{cidade}_2024_2025.json"
        prev_path = TEMP_DIR / f"openmeteo_previous_day1_{cidade}_2024_2025.json"
        if not era5_path.exists() or not prev_path.exists():
            continue
        era5 = json.loads(era5_path.read_text(encoding="utf-8"))
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        df_era5 = pd.DataFrame({"time": era5["hourly"]["time"], "era5": era5["hourly"]["temperature_2m"]})
        df_prev = pd.DataFrame({"time": prev["hourly"]["time"], "previsao": prev["hourly"]["temperature_2m_previous_day1"]})
        merged = pd.merge(df_era5, df_prev, on="time", how="outer")
        merged["era5"] = pd.to_numeric(merged["era5"], errors="coerce")
        merged["previsao"] = pd.to_numeric(merged["previsao"], errors="coerce")
        comp = merged.dropna(subset=["era5", "previsao"])
        erro = comp["previsao"] - comp["era5"]
        mae = float(erro.abs().mean())

        nome_fmt = cidade.replace("_", " ")
        linha = next((l for l in texto.splitlines() if l.startswith(f"| {nome_fmt} |")), None)
        if linha:
            campos = [c.strip() for c in linha.strip("|").split("|")]
            mae_facts = float(campos[2].replace(".", "").replace(",", "."))
            checar(f"{cidade} MAE", round(mae, 4), mae_facts)

    print("\n=== RESUMO ===")
    if erros:
        print(f"\n{len(erros)} DIVERGÊNCIA(S) ENCONTRADA(S):")
        for desc, esp, obt in erros:
            print(f"  - {desc}: facts={esp!r} vs recalculo={obt!r}")
    else:
        print("\nNenhuma divergência encontrada em todos os itens verificados.")


if __name__ == "__main__":
    main()
