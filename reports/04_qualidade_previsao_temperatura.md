# Qualidade da previsão de temperatura day-ahead (conclusão do B5)

Continuação do `reports/03_dst_efeito_e_temperatura.md`, seção B5, que não foi
concluída (o endpoint horário do INMET exige token de reCAPTCHA v3, não contornado).
Nenhuma limpeza, correção ou decisão foi feita. Gerado em 2026-07-17.

**Mudança de fonte de referência:** por instrução explícita, esta conclusão usa ERA5
(reanálise) em vez de estação INMET como referência principal — mesma API, mesmas
coordenadas do relatório 03, sem CAPTCHA. A comparação contra a estação do INMET
(seção 4, opcional) foi feita à parte, via o ZIP anual público (sem CAPTCHA), não pelo
endpoint que exige token.

---

## 1. Fontes e parâmetros exatos

**ERA5 (referência):** `https://archive-api.open-meteo.com/v1/archive`
Parâmetros: `latitude`, `longitude`, `hourly=temperature_2m`, `start_date=2024-01-01`,
`end_date=2025-12-31`, `timezone=America/Sao_Paulo`, **`models=era5`** (explícito —
sem esse parâmetro o endpoint devolve o blend "best_match" de ECMWF IFS + ERA5 +
ERA5-Land, não ERA5 pura).

**Previsão day-ahead:** `https://previous-runs-api.open-meteo.com/v1/forecast`
Parâmetros: `latitude`, `longitude`, `hourly=temperature_2m_previous_day1`,
`start_date=2024-01-01`, `end_date=2025-12-31`, `timezone=America/Sao_Paulo`.

**Coordenadas usadas (idênticas ao relatório 03):**

| Cidade | Latitude pedida | Longitude pedida | Latitude grade ERA5 | Longitude grade ERA5 | Latitude grade previsão | Longitude grade previsão |
|---|---|---|---|---|---|---|
| São Paulo | -23,5505 | -46,6333 | -23,5 | -46,75 | -23,514938 | -46,610504 |
| Rio de Janeiro | -22,9068 | -43,1729 | -22,75 | -43,25 | -22,952549 | -43,215027 |
| Belo Horizonte | -19,9167 | -43,9345 | -20,0 | -44,0 | -19,9297 | -43,966034 |
| Brasília | -15,7797 | -47,9297 | -15,75 | -48,0 | -15,782073 | -47,97168 |
| Goiânia | -16,6869 | -49,2648 | -16,75 | -49,25 | -16,69596 | -49,255005 |

Fato: ERA5 e a Previous Runs API não devolvem o mesmo ponto de grade para a mesma
coordenada pedida — ERA5 arredonda para a grade de 0,25° (ex.: -23,5505 → -23,5); a
Previous Runs API usa uma grade mais fina e diferente (ex.: -23,5505 → -23,514938).
As duas grades ficam a poucos km uma da outra em todas as 5 cidades, não no mesmo
ponto físico exato.

## 2. Alinhamento de timestamp e timezone (confirmado antes de comparar)

| Item | ERA5 | Previsão |
|---|---|---|
| `timezone` retornado | America/Sao_Paulo | America/Sao_Paulo |
| `utc_offset_seconds` | -10800 | -10800 |
| Primeiro timestamp | 2024-01-01T00:00 | 2024-01-01T00:00 |
| Último timestamp | 2025-12-31T23:00 | 2025-12-31T23:00 |
| N linhas | 17.544 | 17.544 |

Nas 5 cidades: 0 timestamps presentes só em ERA5, 0 só na previsão, 17.544 em ambos —
alinhamento exato de rótulo de tempo e fuso horário em todas as 5 cidades, confirmado
antes de qualquer cálculo de erro.

## 3. Comparação previsão-24h vs. ERA5

### 3.1 Resumo por cidade e agregado

| Cidade | N comparável | N descartado (nulo) | MAE geral | RMSE geral | Viés geral | MAE p95 (dias quentes) | N p95 | MAE p5 (dias frios) | N p5 |
|---|---|---|---|---|---|---|---|---|---|
| São Paulo | 17.103 | 441 | 0,9935 | 1,3340 | 0,4060 | 0,9009 | 861 | 1,2300 | 896 |
| Rio de Janeiro | 17.103 | 441 | 1,1419 | 1,5425 | 0,2867 | 1,6744 | 864 | 1,2169 | 899 |
| Belo Horizonte | 17.103 | 441 | 1,0754 | 1,4139 | 0,4203 | 1,0793 | 882 | 1,2260 | 895 |
| Brasília | 17.103 | 441 | 1,0565 | 1,3735 | 0,1228 | 0,9917 | 871 | 1,3483 | 860 |
| Goiânia | 17.103 | 441 | 1,2837 | 1,6828 | 0,8090 | 0,8240 | 894 | 1,6951 | 885 |
| **Agregado (5 cidades)** | 85.515 | 2.205 | **1,1102** | **1,4749** | **0,4090** | 1,1704 | 4.372 | 1,2233 | 4.399 |

Unidade: °C. Erro definido como `previsão − ERA5`; viés positivo = previsão mais
quente que ERA5.

Os 441 timestamps descartados por cidade são todos nulos do lado da previsão (`ERA5`
tem 0 nulos nas 5 cidades) — corresponde exatamente à contagem de nulos já reportada
para a janela jan/2024 em `reports/03_dst_efeito_e_temperatura.md` (441/744), já que a
cobertura da previsão só começa em 2024-01-20 (ver relatório 03, B2).

Fatos lidos da tabela:
- MAE geral por cidade varia de 0,9935 (São Paulo) a 1,2837 (Goiânia).
- Viés é positivo (previsão mais quente que ERA5) em todas as 5 cidades, de 0,1228
  (Brasília) a 0,8090 (Goiânia).
- MAE no p95 (dias mais quentes) é maior que o MAE geral em 2 das 5 cidades (Rio de
  Janeiro: 1,6744 vs. 1,1419; Belo Horizonte: 1,0793 vs. 1,0754) e menor nas outras 3
  (São Paulo, Brasília, Goiânia).
- MAE no p5 (dias mais frios) é maior que o MAE geral em todas as 5 cidades.
- Viés no p5 (dias frios) é positivo e maior que o viés geral em todas as 5 cidades
  (de 0,7234 em Brasília a 1,4441 em Goiânia) — não mostrado na tabela acima, está no
  arquivo de saída `data/interim/comparacao_previsao_era5.json`.

### 3.2 MAE por hora do dia (agregado, 5 cidades)

| Hora local | MAE agregado (5 cidades) |
|---|---|
| 00h | 1,1339 |
| 01h | 1,0967 |
| 02h | 1,1238 |
| 03h | 1,0606 |
| 04h | 1,0292 |
| 05h | 1,0151 |
| 06h | 0,9923 |
| 07h | 1,1479 |
| 08h | 1,0872 |
| 09h | 0,8616 |
| 10h | 0,9492 |
| 11h | 1,1152 |
| 12h | 1,0625 |
| 13h | 1,1253 |
| 14h | 1,1823 |
| 15h | 1,1597 |
| 16h | 1,1687 |
| 17h | 1,1722 |
| **18h** | **1,3182** |
| **19h** | **1,4240** |
| **20h** | **1,2501** |
| 21h | 1,1089 |
| 22h | 1,0449 |
| 23h | 1,0148 |

Menor MAE horário: 09h (0,8616). Maior MAE horário: 19h (1,4240). Nas horas 18h-21h
(janela de pico de carga citada na tarefa), o MAE varia de 1,1089 (21h) a 1,4240
(19h) — as horas 18h, 19h e 20h estão entre as 4 mais altas de todo o perfil de 24h
(as outras 21 horas ficam todas abaixo de 1,19; 18h, 19h e 20h ficam acima de 1,25).
21h fica dentro da faixa comum ao resto do dia (1,1089).

## 4. Comparação opcional — ERA5 vs. estação INMET (São Paulo, A701, 2024)

Concluída, via download em lote (não via endpoint com CAPTCHA).

**Fonte:** `https://portal.inmet.gov.br/uploads/dadoshistoricos/2024.zip` (arquivo
público, ~102 MB, todas as estações automáticas do Brasil, ano de 2024). Extraído o
membro `INMET_SE_SP_A701_SAO PAULO - MIRANTE_01-01-2024_A_31-12-2024.CSV` (estação
identificada no relatório 03: código A701, latitude -23,49638888, longitude
-46,61999999, conforme cabeçalho do próprio arquivo).

**Tratamento aplicado, conforme instrução:**
- Timestamps do INMET publicados em UTC (coluna `Hora UTC`) — convertidos para
  `America/Sao_Paulo` via `zoneinfo`.
- Valores `9999` tratados como ausentes: **0 ocorrências do literal `9999`** foram
  encontradas na coluna de temperatura desta estação neste ano. As ausências reais (19
  no total, de 8.784 linhas) aparecem como célula vazia no CSV, não como o valor
  `9999` — reportado como fato observado, o tratamento de `9999` foi aplicado mas não
  encontrou nenhum caso; o que existe é célula vazia, capturada separadamente.

| Métrica | Valor |
|---|---|
| Linhas brutas da estação (2024) | 8.784 |
| Linhas com data/hora não parseável | 0 |
| Linhas com valor literal `9999` | 0 |
| Linhas com temperatura ausente (célula vazia) | 19 |
| Timestamps em comum com ERA5 (2024) | 8.781 |
| Horas comparáveis (sem nulo em nenhum lado) | 8.762 |
| Horas descartadas | 19 |
| MAE (ERA5 vs. estação INMET A701) | 1,0194 |
| RMSE (ERA5 vs. estação INMET A701) | 1,3557 |
| Viés (INMET − ERA5) | 0,6205 |

Unidade: °C. O MAE entre ERA5 e a estação observada em São Paulo (1,0194) é da mesma
ordem de grandeza do MAE entre a previsão-24h e ERA5 na mesma cidade (0,9935, seção
3.1) — os dois números não são diretamente somáveis nem comparáveis sem mais
processamento (comparam pares de séries diferentes: um é previsão-vs-reanálise, o
outro é reanálise-vs-estação); ambos são reportados aqui como estão, sem combiná-los
em uma métrica única.

## 5. Registro em MANIFEST.json

| Arquivo | Status |
|---|---|
| `era5_temperature_2m_{cidade}_2024_2025.json` × 5 | baixado e registrado |
| `openmeteo_previous_day1_{cidade}_2024_2025.json` × 5 | baixado e registrado |
| `inmet_dadoshistoricos_2024.zip` | baixado e registrado (102.772.199 bytes, sha256 `0a7f89de57427f79...`) |

11 arquivos novos em `data/raw/temperatura/`, todos com URL, timestamp local/UTC,
tamanho em bytes e SHA-256 em `data/raw/MANIFEST.json`, no mesmo esquema usado para os
arquivos do ONS. Nenhum arquivo do ONS em `data/raw/` foi alterado.

---

## Reprodutibilidade

- Ambiente: Python 3.12.10, `numpy`, `pandas`, dependências pinadas em
  [`requirements.txt`](../requirements.txt).
- Scripts: [`src/download_temperatura_era5.py`](../src/download_temperatura_era5.py)
  (download ERA5 + previsão), [`src/comparar_previsao_era5.py`](../src/comparar_previsao_era5.py)
  (seção 3), [`src/comparar_inmet_era5.py`](../src/comparar_inmet_era5.py) (seção 4).
- Saídas intermediárias: [`data/interim/comparacao_previsao_era5.json`](../data/interim/comparacao_previsao_era5.json)
  (todas as métricas por cidade e agregadas, incluindo os campos não tabulados aqui),
  [`data/interim/comparacao_inmet_era5.json`](../data/interim/comparacao_inmet_era5.json).
- Nenhum CAPTCHA foi contornado. Nenhum cadastro foi criado. Nenhuma autenticação foi
  feita em nenhum serviço.
- Nenhuma aleatoriedade foi usada em nenhuma etapa desta sondagem.
