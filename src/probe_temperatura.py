"""Parte B: viabilidade de temperatura sem vazamento (Open-Meteo Previous Runs API).

B1: endpoint e parâmetros documentados.
B2: teste de 3 janelas de 1 mês, 5 cidades, temperature_2m_previous_day1.
B3: bisecção para achar a data mais antiga com dado.
B4: checagem de disponibilidade de previous_day2.

Não altera nada em data/raw/ do ONS. Não baixa anos inteiros.
"""
import json
from pathlib import Path

import pandas as pd
import requests

INTERIM_DIR = Path(__file__).resolve().parent.parent / "data" / "interim"
BASE_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"

CIDADES = {
    "Sao_Paulo": (-23.5505, -46.6333),
    "Rio_de_Janeiro": (-22.9068, -43.1729),
    "Belo_Horizonte": (-19.9167, -43.9345),
    "Brasilia": (-15.7797, -47.9297),
    "Goiania": (-16.6869, -49.2648),
}

JANELAS_TESTE = [
    ("2021-03-01", "2021-03-31"),
    ("2024-01-01", "2024-01-31"),
    ("2026-01-01", "2026-01-31"),
]


def chamar_api(lat, lon, hourly_var, start_date, end_date, timezone="America/Sao_Paulo"):
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": hourly_var,
        "start_date": start_date, "end_date": end_date,
        "timezone": timezone,
    }
    try:
        r = requests.get(BASE_URL, params=params, timeout=60)
    except requests.RequestException as e:
        return {"status": "erro_rede", "erro": str(e), "url": None}
    resultado = {"status_code": r.status_code, "url": r.url}
    if r.status_code == 200:
        resultado["status"] = "ok"
        resultado["json"] = r.json()
    else:
        resultado["status"] = "erro_http"
        try:
            resultado["corpo"] = r.json()
        except Exception:
            resultado["corpo"] = r.text[:500]
    return resultado


def horas_esperadas(start_date, end_date):
    d0 = pd.Timestamp(start_date)
    d1 = pd.Timestamp(end_date)
    return int((d1 - d0).days + 1) * 24


def b2_testar_janelas():
    print("=" * 100)
    print("B2: teste de 3 janelas x 5 cidades, temperature_2m_previous_day1")
    print("=" * 100)
    resultado = []
    for cidade, (lat, lon) in CIDADES.items():
        for start, end in JANELAS_TESTE:
            r = chamar_api(lat, lon, "temperature_2m_previous_day1", start, end)
            esperado = horas_esperadas(start, end)
            linha = {
                "cidade": cidade, "lat": lat, "lon": lon,
                "janela": f"{start}_a_{end}", "status": r["status"], "url": r.get("url"),
            }
            if r["status"] == "ok":
                j = r["json"]
                tempos = j["hourly"]["time"]
                valores = j["hourly"]["temperature_2m_previous_day1"]
                n_nulos = sum(1 for v in valores if v is None)
                linha.update({
                    "n_horas_retornadas": len(tempos),
                    "n_horas_esperadas": esperado,
                    "n_nulos": n_nulos,
                    "timezone_retornado": j.get("timezone"),
                    "utc_offset_seconds": j.get("utc_offset_seconds"),
                    "timezone_abbreviation": j.get("timezone_abbreviation"),
                    "primeiro_timestamp": tempos[0] if tempos else None,
                    "ultimo_timestamp": tempos[-1] if tempos else None,
                })
            else:
                linha.update({"erro_detalhe": r.get("corpo", r.get("erro"))})
            print(json.dumps(linha, ensure_ascii=False, default=str))
            resultado.append(linha)
    with open(INTERIM_DIR / "temperatura_b2_janelas.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    return resultado


def b3_bissecao_data_mais_antiga():
    print("\n" + "=" * 100)
    print("B3: bisseção para achar a data mais antiga com dado (Sao Paulo, GFS temperature_2m_previous_day1)")
    print("=" * 100)
    lat, lon = CIDADES["Sao_Paulo"]

    def tem_dado(data_str):
        r = chamar_api(lat, lon, "temperature_2m_previous_day1", data_str, data_str)
        if r["status"] != "ok":
            return False, r
        valores = r["json"]["hourly"]["temperature_2m_previous_day1"]
        tem = any(v is not None for v in valores)
        return tem, r

    baixo = pd.Timestamp("2015-01-01")  # certamente sem dado
    alto = pd.Timestamp("2021-06-01")   # certamente com dado (declarado GFS desde mar/2021)

    ok_alto, r_alto = tem_dado(str(alto.date()))
    ok_baixo, r_baixo = tem_dado(str(baixo.date()))
    print(f"checagem limite inferior {baixo.date()}: tem_dado={ok_baixo}")
    print(f"checagem limite superior {alto.date()}: tem_dado={ok_alto}")

    passos = []
    while (alto - baixo).days > 1:
        meio = baixo + (alto - baixo) / 2
        meio = pd.Timestamp(meio.date())
        tem, r = tem_dado(str(meio.date()))
        passos.append({"data_testada": str(meio.date()), "tem_dado": tem})
        print(f"  bisseção: {meio.date()} -> tem_dado={tem}")
        if tem:
            alto = meio
        else:
            baixo = meio

    resultado = {
        "limite_inferior_sem_dado": str(baixo.date()),
        "limite_superior_com_dado": str(alto.date()),
        "passos_bissecao": passos,
    }
    print(f"Resultado: sem dado até {baixo.date()} (inclusive), com dado a partir de {alto.date()}")
    with open(INTERIM_DIR / "temperatura_b3_bissecao.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    return resultado


def b4_previous_day2():
    print("\n" + "=" * 100)
    print("B4: disponibilidade de temperature_2m_previous_day2 (48h)")
    print("=" * 100)
    lat, lon = CIDADES["Sao_Paulo"]
    resultado = []
    for start, end in JANELAS_TESTE:
        r = chamar_api(lat, lon, "temperature_2m_previous_day2", start, end)
        linha = {"janela": f"{start}_a_{end}", "status": r["status"]}
        if r["status"] == "ok":
            valores = r["json"]["hourly"].get("temperature_2m_previous_day2", [])
            n_nulos = sum(1 for v in valores if v is None)
            linha.update({"n_horas_retornadas": len(valores), "n_nulos": n_nulos})
        else:
            linha["erro_detalhe"] = r.get("corpo", r.get("erro"))
        print(json.dumps(linha, ensure_ascii=False, default=str))
        resultado.append(linha)
    with open(INTERIM_DIR / "temperatura_b4_previous_day2.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    return resultado


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    b2_testar_janelas()
    b3_bissecao_data_mais_antiga()
    b4_previous_day2()


if __name__ == "__main__":
    main()
