"""Explica o buraco de 3h em UTC nas 5 viradas de fim de DST (fevereiro).
Não corrige, não decide — só extrai, converte e reporta.

Saída: data/interim/fev_gap_*.json
"""
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
ANOS = list(range(2015, 2027))
TZ = ZoneInfo("America/Sao_Paulo")

# (sábado, domingo) de cada virada de fim de DST
VIRADAS = [
    ("2015-02-21", "2015-02-22"),
    ("2016-02-20", "2016-02-21"),
    ("2017-02-18", "2017-02-19"),
    ("2018-02-17", "2018-02-18"),
    ("2019-02-16", "2019-02-17"),
]


def load_all() -> pd.DataFrame:
    frames = []
    for ano in ANOS:
        fpath = RAW_DIR / f"CURVA_CARGA_{ano}.parquet"
        if not fpath.exists():
            continue
        df = pd.read_parquet(
            fpath, columns=["id_subsistema", "din_instante", "val_cargaenergiahomwmed"]
        )
        df["id_subsistema"] = df["id_subsistema"].astype(str)
        df["val_raw_str"] = df["val_cargaenergiahomwmed"].astype(str)
        df["val_num"] = pd.to_numeric(df["val_cargaenergiahomwmed"], errors="coerce")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def task_1_2_janelas(full: pd.DataFrame):
    print("\n" + "=" * 100)
    print("TASK 1+2: janelas brutas (N e SE lado a lado) + conversão UTC linha a linha (SE)")
    print("=" * 100)
    resultado = []
    for sab, dom in VIRADAS:
        sab_dt = pd.Timestamp(sab)
        inicio = sab_dt + pd.Timedelta(hours=20)
        fim = sab_dt + pd.Timedelta(days=1, hours=6)
        print(f"\n--- Virada {sab} / {dom} --- janela [{inicio} , {fim}] ---")

        janela = full[(full["din_instante"] >= inicio) & (full["din_instante"] <= fim)]

        n_sub = janela[janela["id_subsistema"] == "N"].sort_values("din_instante")
        se_sub = janela[janela["id_subsistema"] == "SE"].sort_values("din_instante")

        print(f"{'din_instante':<20} {'N (val bruto)':<18} {'SE (val bruto)':<18} {'SE -> UTC':<28} {'classificação':<15}")
        registro_virada = []
        se_idx = se_sub.set_index("din_instante")
        n_idx = n_sub.set_index("din_instante")
        todos_ts = sorted(set(se_idx.index) | set(n_idx.index))
        for ts in todos_ts:
            val_n = n_idx.loc[ts, "val_raw_str"] if ts in n_idx.index else "(sem linha)"
            val_se = se_idx.loc[ts, "val_raw_str"] if ts in se_idx.index else "(sem linha)"

            classificacao = "ok"
            utc_str = ""
            try:
                # checagem explícita de ambiguidade/inexistência via zoneinfo (fold=0 vs fold=1)
                exists_fold0 = dt.datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, tzinfo=TZ, fold=0)
                exists_fold1 = dt.datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, tzinfo=TZ, fold=1)
                utc0 = exists_fold0.astimezone(dt.timezone.utc)
                utc1 = exists_fold1.astimezone(dt.timezone.utc)
                if utc0 != utc1:
                    # ambíguo (2 instantes físicos reais) OU inexistente (nenhum instante físico real)
                    # distinguir: ambíguo se a hora local está dentro do intervalo repetido (offset local igual em ambos os folds coincide com um antes/depois real)
                    # heurística exata via zoneinfo: comparar se o horário local existe fisicamente checando
                    # se fold=0 reproduz o mesmo horário local quando convertido de volta
                    back0 = utc0.astimezone(TZ)
                    inexistente = (back0.hour, back0.minute) != (ts.hour, ts.minute)
                    classificacao = "INEXISTENTE" if inexistente else "AMBÍGUO"
                    utc_str = f"fold0={utc0} | fold1={utc1}"
                else:
                    utc_str = str(utc0)
                    classificacao = "ok (não ambíguo/inexistente)"
            except Exception as e:
                classificacao = f"erro:{e}"

            print(f"{str(ts):<20} {val_n:<18} {val_se:<18} {utc_str:<28} {classificacao:<15}")
            registro_virada.append({
                "din_instante": str(ts), "val_N": val_n, "val_SE": val_se,
                "classificacao": classificacao, "utc": utc_str,
            })
        resultado.append({"sabado": sab, "domingo": dom, "janela": registro_virada})

    with open(INTERIM_DIR / "fev_gap_janelas.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    return resultado


def task_3_horas_faltantes():
    print("\n" + "=" * 100)
    print("TASK 3: instantes UTC exatos ausentes em cada virada (raise em ambíguo/inexistente, drop da linha)")
    print("=" * 100)
    resultado = []
    for sab, dom in VIRADAS:
        sab_dt = pd.Timestamp(sab)
        # local antes e depois da hora ambígua, para cravar o UTC efetivamente produzido
        antes = dt.datetime(sab_dt.year, sab_dt.month, sab_dt.day, 22, 0, 0, tzinfo=TZ)
        depois = dt.datetime(sab_dt.year, sab_dt.month, sab_dt.day + 1, 0, 0, 0, tzinfo=TZ)
        utc_antes = antes.astimezone(dt.timezone.utc)
        utc_depois = depois.astimezone(dt.timezone.utc)
        faltantes = []
        cursor = utc_antes + dt.timedelta(hours=1)
        while cursor < utc_depois:
            faltantes.append(cursor)
            cursor += dt.timedelta(hours=1)
        print(f"Virada {sab}/{dom}: UTC antes={utc_antes}, UTC depois={utc_depois}, faltantes={[str(f) for f in faltantes]}")
        resultado.append({
            "sabado": sab, "domingo": dom,
            "utc_ultimo_antes_do_buraco": str(utc_antes),
            "utc_primeiro_depois_do_buraco": str(utc_depois),
            "utc_faltantes": [str(f) for f in faltantes],
        })
    with open(INTERIM_DIR / "fev_gap_horas_faltantes.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    return resultado


def task_4_hipotese_soma(full: pd.DataFrame):
    print("\n" + "=" * 100)
    print("TASK 4: valor da hora ambígua e vizinhas vs. média das mesmas horas 3 domingos antes/depois (SE/CO)")
    print("=" * 100)
    se = full[full["id_subsistema"] == "SE"].set_index("din_instante")["val_num"]
    resultado = []
    for sab, dom in VIRADAS:
        sab_dt = pd.Timestamp(sab)
        pontos = {
            "sab_21:00": sab_dt + pd.Timedelta(hours=21),
            "sab_22:00": sab_dt + pd.Timedelta(hours=22),
            "sab_23:00_AMBIGUA": sab_dt + pd.Timedelta(hours=23),
            "dom_00:00": sab_dt + pd.Timedelta(days=1, hours=0),
            "dom_01:00": sab_dt + pd.Timedelta(days=1, hours=1),
            "dom_02:00": sab_dt + pd.Timedelta(days=1, hours=2),
        }
        print(f"\n--- Virada {sab}/{dom} ---")
        linha_virada = {"sabado": sab, "domingo": dom, "pontos": []}
        for nome, ts in pontos.items():
            observado = se.get(ts, float("nan"))
            refs = []
            for delta_dias in (-21, -14, -7, 7, 14, 21):
                ts_ref = ts + pd.Timedelta(days=delta_dias)
                v = se.get(ts_ref, float("nan"))
                refs.append((str(ts_ref), v))
            refs_validos = [v for _, v in refs if pd.notna(v)]
            media_ref = sum(refs_validos) / len(refs_validos) if refs_validos else float("nan")
            razao = observado / media_ref if (pd.notna(observado) and media_ref) else float("nan")
            print(f"  {nome} ({ts}): observado={observado} media_ref(6 pontos)={media_ref:.2f} razao={razao:.4f}" if pd.notna(razao) else f"  {nome} ({ts}): observado={observado} media_ref=N/A razao=N/A")
            linha_virada["pontos"].append({
                "rotulo": nome, "din_instante": str(ts), "valor_observado": observado,
                "referencias": refs, "media_referencia": media_ref, "razao_observado_sobre_media": razao,
            })
        resultado.append(linha_virada)
    with open(INTERIM_DIR / "fev_gap_hipotese_soma.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    return resultado


def task_5_metodos_conversao(full: pd.DataFrame):
    print("\n" + "=" * 100)
    print("TASK 5: métodos alternativos de conversão UTC (fold=0, fold=1, offset fixo -3, offset fixo -2) — SE/CO completo")
    print("=" * 100)
    se = full[full["id_subsistema"] == "SE"].copy()
    ts_list = se["din_instante"].tolist()
    resultado = {}

    def conv_fold(fold):
        out = []
        for ts in ts_list:
            d = dt.datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, tzinfo=TZ, fold=fold)
            out.append(d.astimezone(dt.timezone.utc))
        return out

    def conv_fixo(offset_horas):
        tzfix = dt.timezone(dt.timedelta(hours=offset_horas))
        out = []
        for ts in ts_list:
            d = dt.datetime(ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, tzinfo=tzfix)
            out.append(d.astimezone(dt.timezone.utc))
        return out

    for nome, valores in [
        ("fold=0", conv_fold(0)),
        ("fold=1", conv_fold(1)),
        ("offset_fixo_UTC-3", conv_fixo(-3)),
        ("offset_fixo_UTC-2", conv_fixo(-2)),
    ]:
        n_total = len(valores)
        n_distintos = len(set(valores))
        n_duplicatas = n_total - n_distintos
        print(f"{nome}: linhas={n_total} utc_distintos={n_distintos} duplicatas={n_duplicatas}")
        resultado[nome] = {"linhas": n_total, "utc_distintos": n_distintos, "duplicatas": n_duplicatas}

    with open(INTERIM_DIR / "fev_gap_metodos.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    return resultado


def task_6_contagem_registros(full: pd.DataFrame):
    print("\n" + "=" * 100)
    print("TASK 6: contagem de registros por subsistema, na data de virada e no dia seguinte")
    print("=" * 100)
    resultado = []
    for sab, dom in VIRADAS:
        dom_dt = pd.Timestamp(dom)
        dia_seguinte = dom_dt + pd.Timedelta(days=1)
        for data_alvo, rotulo in [(pd.Timestamp(sab), "sabado(virada)"), (dom_dt, "domingo(virada)"), (dia_seguinte, "dia_seguinte")]:
            contagem = {}
            for sub in ["N", "NE", "S", "SE"]:
                n = len(full[(full["id_subsistema"] == sub) & (full["din_instante"].dt.date == data_alvo.date())])
                contagem[sub] = n
            print(f"{rotulo} {data_alvo.date()}: {contagem}")
            resultado.append({"data": str(data_alvo.date()), "rotulo": rotulo, "contagem": contagem})
    with open(INTERIM_DIR / "fev_gap_contagem.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    return resultado


def main():
    full = load_all()
    print(f"Total linhas carregadas: {len(full)}")
    task_1_2_janelas(full)
    task_3_horas_faltantes()
    task_4_hipotese_soma(full)
    task_5_metodos_conversao(full)
    task_6_contagem_registros(full)


if __name__ == "__main__":
    main()
