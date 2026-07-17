"""Gera data/processed/carga_se.parquet — a série limpa do SE/CO para modelagem.

Execução de decisões já tomadas (reports/FACTS.md, seção H). Não é sondagem: não
imputa, não remove outlier, não cria feature. Se um sanity check falhar, o script
ABORTA (raise) — não conserta nada.
"""
import math
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
FACTS_PATH = REPORTS_DIR / "FACTS.md"
OUT_PATH = PROCESSED_DIR / "carga_se.parquet"
ANOS = list(range(2015, 2027))
TZ = ZoneInfo("America/Sao_Paulo")

# Valores documentados em reports/FACTS.md, usados só para checagem — não recalculados
# aqui, e não usados para corrigir nada caso divirjam (o script aborta).
FACTS_SE_N_LINHAS = 101_136
FACTS_SE_PRIMEIRO_INSTANTE = "2015-01-01 00:00:00"
FACTS_SE_ULTIMO_INSTANTE = "2026-07-15 23:00:00"
FACTS_SE_DUPLICADOS = 0
FACTS_SE_DIAS_IRREGULARES = 0

# Tolerância para comparar agregados (min/max/média/mediana) calculados aqui contra
# os mesmos agregados lidos de reports/FACTS.md seção C. Os dois lados vêm de
# pipelines de arredondamento diferentes (float cru vs. round para exibição em
# pt-BR com 3 casas), então igualdade estrita não é o critério certo.
RTOL_AGREGADOS = 1e-6
ABS_TOL_AGREGADOS = 1e-6  # piso absoluto, evita falso positivo perto de zero


class SanityCheckError(RuntimeError):
    pass


def gerar_timestamps_dst() -> list[str]:
    """Mesma lógica de src/gerar_facts.py — via zoneinfo/IANA, nenhuma data
    hardcoded. Varre hora a hora 2015-01-01 a 2019-12-31 e classifica cada
    timestamp local usando fold=0/fold=1."""
    def classificar(ts: pd.Timestamp) -> str:
        d0 = datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, tzinfo=TZ, fold=0)
        d1 = datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, tzinfo=TZ, fold=1)
        u0 = d0.astimezone(timezone.utc)
        u1 = d1.astimezone(timezone.utc)
        if u0 == u1:
            return "ok"
        back0 = u0.astimezone(TZ)
        return "inexistente" if (back0.hour, back0.minute) != (ts.hour, ts.minute) else "ambiguo"

    horas = pd.date_range("2015-01-01", "2020-01-01", freq="h", inclusive="left")
    especiais = [str(h) for h in horas if classificar(h) != "ok"]
    if len(especiais) != 9:
        raise SanityCheckError(
            f"Geração de timestamps de DST via zoneinfo produziu {len(especiais)}, esperado 9 (FACTS.md seção D)."
        )
    return sorted(especiais)


def verificar_roundtrip_string(val_raw_str: pd.Series) -> None:
    """Para cada string não-vazia, confirma que Decimal(original) == Decimal(str(float(original))).
    Zeros à direita suprimidos pelo float() não contam como perda (a comparação é
    numérica via Decimal, não textual). ABORTA se encontrar perda real."""
    nao_vazias = val_raw_str[val_raw_str.str.strip() != ""]
    perdas = []
    for s in nao_vazias.unique():
        try:
            d_original = Decimal(s)
        except InvalidOperation:
            perdas.append((s, "não parseável como Decimal"))
            continue
        f = float(s)
        d_via_float = Decimal(str(f))
        if d_original != d_via_float:
            perdas.append((s, f"Decimal original={d_original} != Decimal via float={d_via_float}"))
    if perdas:
        raise SanityCheckError(f"Perda de precisão real no round-trip float, {len(perdas)} valor(es): {perdas[:5]}")


def parse_valor_br(s: str) -> float:
    """Converte um número no formato pt-BR usado pelo FACTS.md ('62.149,885':
    '.' separador de milhar, ',' decimal) para float."""
    return float(s.strip().replace(".", "").replace(",", "."))


def ler_estatisticas_se_do_facts() -> dict:
    """Lê reports/FACTS.md, seção C ('Estatística de valor'), linha do subsistema SE,
    e devolve mínimo/máximo/média/mediana (float) e os timestamps de mínimo/máximo
    (str). Parsing de texto direto do arquivo — este script não reexecuta
    src/gerar_facts.py, então se a seção mudar de formato isto precisa abortar,
    não adivinhar."""
    if not FACTS_PATH.exists():
        raise SanityCheckError(f"FACTS.md ausente: {FACTS_PATH}")
    texto = FACTS_PATH.read_text(encoding="utf-8")
    idx = texto.find("Estatística de valor")
    if idx == -1:
        raise SanityCheckError("Seção 'Estatística de valor' não encontrada em FACTS.md — não é possível conferir agregados do SE.")
    trecho = texto[idx:idx + 4000]
    linha = next((l for l in trecho.splitlines() if l.startswith("| SE |")), None)
    if linha is None:
        raise SanityCheckError("Linha 'SE' da tabela de estatísticas não encontrada em FACTS.md.")
    campos = [c.strip() for c in linha.strip("|").split("|")]
    if len(campos) != 11:
        raise SanityCheckError(f"Linha SE da tabela de estatísticas tem {len(campos)} campos, esperado 11: {campos}")
    # campos: subsistema, n_validos, minimo, ts_min, maximo, ts_max, media, mediana, desvio, q25, q75
    return {
        "minimo": parse_valor_br(campos[2]),
        "timestamp_minimo": campos[3],
        "maximo": parse_valor_br(campos[4]),
        "timestamp_maximo": campos[5],
        "media": parse_valor_br(campos[6]),
        "mediana": parse_valor_br(campos[7]),
    }


def carregar_se() -> tuple[pd.DataFrame, dict]:
    frames = []
    linhas_por_ano = {}
    for ano in ANOS:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        if not fpath.exists():
            raise SanityCheckError(f"Arquivo ausente: {fpath}")
        df = pd.read_parquet(fpath)
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        df_se = df[df["id_subsistema"] == "SE"].copy()
        linhas_por_ano[ano] = len(df_se)

        # round-trip só se aplica aos anos em que a coluna é texto
        if df_se["val_cargaenergiahomwmed"].dtype == object or str(df_se["val_cargaenergiahomwmed"].dtype) == "str":
            verificar_roundtrip_string(df_se["val_cargaenergiahomwmed"].astype(str))
            val_raw_str = df_se["val_cargaenergiahomwmed"].astype(str)
            val_num = pd.to_numeric(val_raw_str.replace("", None), errors="coerce")
        else:
            val_num = pd.to_numeric(df_se["val_cargaenergiahomwmed"], errors="coerce")

        df_se["val_cargaenergiahomwmed"] = val_num.astype("float64")
        df_se["ano_arquivo"] = ano
        frames.append(df_se[["id_subsistema", "din_instante", "val_cargaenergiahomwmed", "ano_arquivo"]])

    full = pd.concat(frames, ignore_index=True)
    return full, linhas_por_ano


def main():
    print("Carregando os 12 anos, filtrando id_subsistema == 'SE'...")
    full, linhas_por_ano = carregar_se()

    # --- SANITY CHECK 1: contagem de linhas bate com a soma dos anos filtrados por SE
    soma_anos = sum(linhas_por_ano.values())
    if soma_anos != len(full):
        raise SanityCheckError(f"Soma por ano ({soma_anos}) != total concatenado ({len(full)}).")
    if len(full) != FACTS_SE_N_LINHAS:
        raise SanityCheckError(
            f"Total de linhas do SE ({len(full)}) diverge de reports/FACTS.md seção C ({FACTS_SE_N_LINHAS})."
        )

    # din_instante: já é datetime tz-naive no parquet de origem, representando hora
    # local America/Sao_Paulo (fato derivado, reports/FACTS.md seção K3). Não convertido.
    full["din_instante"] = pd.to_datetime(full["din_instante"])
    if full["din_instante"].dt.tz is not None:
        raise SanityCheckError("din_instante não é tz-naive — esperado naive representando hora local.")

    # ordenar e checar duplicata
    full = full.sort_values("din_instante").reset_index(drop=True)
    n_duplicados = int(full["din_instante"].duplicated().sum())
    if n_duplicados != FACTS_SE_DUPLICADOS:
        raise SanityCheckError(f"{n_duplicados} timestamps duplicados, esperado {FACTS_SE_DUPLICADOS} (FACTS.md seção C).")

    # --- SANITY CHECK 2: primeiro/último instante batem com FACTS.md seção C
    primeiro = str(full["din_instante"].iloc[0])
    ultimo = str(full["din_instante"].iloc[-1])
    if primeiro != FACTS_SE_PRIMEIRO_INSTANTE or ultimo != FACTS_SE_ULTIMO_INSTANTE:
        raise SanityCheckError(
            f"Período [{primeiro}, {ultimo}] diverge de FACTS.md seção C "
            f"[{FACTS_SE_PRIMEIRO_INSTANTE}, {FACTS_SE_ULTIMO_INSTANTE}]."
        )

    # --- is_dst_transition: gerado via zoneinfo, não hardcoded
    timestamps_dst = gerar_timestamps_dst()
    full["is_dst_transition"] = full["din_instante"].astype(str).isin(timestamps_dst)
    n_flags = int(full["is_dst_transition"].sum())
    # das 9 datas, as 5 ambíguas (fim de DST) têm valor presente (não vazio) para SE
    # (reports/FACTS.md seção D); só as 4 inexistentes (início de DST) ficam vazias
    # para SE. O flag marca as 9, independente de o valor estar presente ou vazio.
    if n_flags != 9:
        raise SanityCheckError(f"is_dst_transition marcou {n_flags} linhas, esperado 9 (todas as 9 datas existem como linha para SE).")

    # --- SANITY CHECK 3: NaN só onde já documentado no FACTS.md
    nan_mask = full["val_cargaenergiahomwmed"].isna()
    nan_timestamps = set(full.loc[nan_mask, "din_instante"].astype(str))

    # os 4 timestamps de início de DST (inexistentes) — vazios para SE, per FACTS.md seção D
    inicio_dst_esperados = {"2015-10-18 00:00:00", "2016-10-16 00:00:00", "2017-10-15 00:00:00", "2018-11-04 00:00:00"}
    dia_2015_04_09 = set(str(t) for t in full["din_instante"] if t.date() == pd.Timestamp("2015-04-09").date())

    nan_esperados = inicio_dst_esperados | dia_2015_04_09
    nan_inesperados = nan_timestamps - nan_esperados
    if nan_inesperados:
        raise SanityCheckError(f"NaN em timestamps não documentados no FACTS.md: {sorted(nan_inesperados)[:10]}")

    faltando_nan_esperado = nan_esperados - nan_timestamps
    if faltando_nan_esperado:
        raise SanityCheckError(
            f"Timestamps documentados como vazios no FACTS.md NÃO estão NaN na série limpa: "
            f"{sorted(faltando_nan_esperado)[:10]}"
        )

    # --- SANITY CHECK 4: mínimo, máximo, média e mediana batem com FACTS.md seção C,
    # lidos do arquivo em tempo de execução (não hardcoded) — pega regressão silenciosa
    # se a limpeza mudar. Tolerância explícita porque os dois lados vêm de pipelines de
    # arredondamento diferentes (float cru vs. exibição pt-BR com 3 casas).
    valido = full.dropna(subset=["val_cargaenergiahomwmed"])
    idx_min = valido["val_cargaenergiahomwmed"].idxmin()
    idx_max = valido["val_cargaenergiahomwmed"].idxmax()
    valor_min = float(valido.loc[idx_min, "val_cargaenergiahomwmed"])
    ts_min = str(valido.loc[idx_min, "din_instante"])
    valor_max = float(valido.loc[idx_max, "val_cargaenergiahomwmed"])
    ts_max = str(valido.loc[idx_max, "din_instante"])
    valor_media = float(valido["val_cargaenergiahomwmed"].mean())
    valor_mediana = float(valido["val_cargaenergiahomwmed"].median())

    facts_estat = ler_estatisticas_se_do_facts()
    divergencias = []
    if ts_min != facts_estat["timestamp_minimo"]:
        divergencias.append(f"timestamp mínimo: calculado={ts_min} facts={facts_estat['timestamp_minimo']}")
    if ts_max != facts_estat["timestamp_maximo"]:
        divergencias.append(f"timestamp máximo: calculado={ts_max} facts={facts_estat['timestamp_maximo']}")
    agregados_calculados = {"minimo": valor_min, "maximo": valor_max, "media": valor_media, "mediana": valor_mediana}
    for nome, valor_calculado in agregados_calculados.items():
        valor_facts = facts_estat[nome]
        if not math.isclose(valor_calculado, valor_facts, rel_tol=RTOL_AGREGADOS, abs_tol=ABS_TOL_AGREGADOS):
            divergencias.append(f"{nome}: calculado={valor_calculado} facts={valor_facts}")
    if divergencias:
        raise SanityCheckError(f"Agregados do SE divergem de FACTS.md seção C: {'; '.join(divergencias)}")

    # --- SANITY CHECK 5: todos os dias têm 24 registros, exceto os já documentados (nenhum, para SE)
    dia = full["din_instante"].dt.date
    contagem_por_dia = dia.value_counts()
    calendario_completo = pd.date_range(full["din_instante"].min().normalize(), full["din_instante"].max().normalize(), freq="D").date
    contagem_por_dia = contagem_por_dia.reindex(calendario_completo, fill_value=0)
    dias_irregulares = contagem_por_dia[contagem_por_dia != 24]
    if len(dias_irregulares) != FACTS_SE_DIAS_IRREGULARES:
        raise SanityCheckError(
            f"{len(dias_irregulares)} dias irregulares (!=24 registros) para SE, esperado {FACTS_SE_DIAS_IRREGULARES} "
            f"(FACTS.md seção C). Dias: {dias_irregulares.to_dict()}"
        )

    # --- gravação
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    saida = full[["din_instante", "val_cargaenergiahomwmed", "is_dst_transition"]].copy()
    saida.to_parquet(OUT_PATH, index=False)

    # --- resumo no stdout
    print("\n=== RESUMO ===")
    print(f"Arquivo: {OUT_PATH}")
    print(f"Linhas: {len(saida)}")
    print(f"Período: {primeiro} a {ultimo}")
    print(f"NaN em val_cargaenergiahomwmed: {int(nan_mask.sum())}")
    print(f"is_dst_transition == True: {n_flags}")
    print(f"Valor mínimo: {valor_min} @ {ts_min}")
    print(f"Valor máximo: {valor_max} @ {ts_max}")
    print(f"Valor médio: {valor_media:.4f}")
    print(f"Valor mediano: {valor_mediana:.4f}")
    print("Todos os sanity checks passaram (agregados conferidos contra FACTS.md seção C, automaticamente).")


if __name__ == "__main__":
    try:
        main()
    except SanityCheckError as e:
        print(f"\nSANITY CHECK FALHOU — ABORTADO: {e}", file=sys.stderr)
        sys.exit(1)
