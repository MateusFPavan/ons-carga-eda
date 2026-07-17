# FACTS.md — Folha de Fatos Canônica do Projeto 3

Fonte única de números para escopo, README e relatórios futuros. Todo valor
abaixo é recalculado por [`src/gerar_facts.py`](../src/gerar_facts.py) a partir
de `data/raw/*.parquet`, `data/raw/MANIFEST.json` e `data/raw/temperatura/*`
(já baixados; este script não faz nenhuma requisição de rede). Nenhum número
foi digitado à mão nem copiado dos relatórios 00–04. Re-executar este script
produz o mesmo arquivo.

---

## A. Proveniência

- Fonte: ONS — Curva de Carga Horária. URL base: `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/curva-carga-ho`
- Licença: CC-BY (declarada pelo portal de dados abertos do ONS — não é um valor
  extraído do parquet ou do manifesto, listada aqui como contexto fixo)
- Arquivos: 12, anos cobertos: 2015–2026 (12 arquivos, 1 por ano)
- Snapshot baixado entre `2026-07-16T20:06:20.964290-03:00` e `2026-07-16T20:06:42.927332-03:00`
- SHA-256 do `MANIFEST.json` neste momento: `7d73b975aa6b9da6cd7245bafb120c32fc97d4269c08faee545b210e633cb723`
- Total de entradas no manifesto (inclui arquivos de temperatura de sessões posteriores): 41

**Aviso — republicação em lote (recalculado, não copiado):** agrupando os 12
arquivos por data (não hora) do cabeçalho HTTP `Last-Modified`:

| Data (Last-Modified) | Anos |
|---|---|
| 09 Oct 2025 | 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024 |
| 31 Jan 2026 | 2025 |
| 16 Jul 2026 | 2026 |

Os 10 arquivos de 2015–2024 compartilham a mesma DATA de `Last-Modified`
(não o mesmo timestamp exato ao segundo — os horários formam uma sequência de
poucos minutos, consistente com republicação em lote, não com 10 eventos
independentes). O ONS declara um "processo de consistência recorrente" que
revisa dados retroativamente — por isso este snapshot é identificado por hash,
não assumido como imutável.

---

## B. Esquema e divergências contra o dicionário oficial

| Ano | Linhas | Colunas divergem | dtype de `val_cargaenergiahomwmed` | Strings vazias |
|---|---|---|---|---|
| 2015 | 35.016 | nenhuma | `str` | 76 |
| 2016 | 35.136 | nenhuma | `str` | 4 |
| 2017 | 35.040 | nenhuma | `str` | 4 |
| 2018 | 35.040 | nenhuma | `str` | 3 |
| 2019 | 35.040 | nenhuma | `str` | 0 |
| 2020 | 35.136 | nenhuma | `str` | 0 |
| 2021 | 35.040 | nenhuma | `str` | 0 |
| 2022 | 35.040 | nenhuma | `str` | 0 |
| 2023 | 35.040 | nenhuma | `str` | 0 |
| 2024 | 35.136 | nenhuma | `str` | 0 |
| 2025 | 35.040 | nenhuma | `float64` | 0 |
| 2026 | 18.816 | nenhuma | `float64` | 0 |

**Total de strings vazias recalculado: 87** (coluna
declarada pelo dicionário como não permitindo nulo).

`id_subsistema`: `N`, `NE`, `S`, `SE` — estável nos 12 anos: **sim**.

`nom_subsistema` para o código `SE`, por ano:

| Ano | nom_subsistema (SE) |
|---|---|
| 2015 | SUDESTE |
| 2016 | SUDESTE |
| 2017 | SUDESTE |
| 2018 | SUDESTE |
| 2019 | SUDESTE |
| 2020 | SUDESTE |
| 2021 | SUDESTE |
| 2022 | SUDESTE |
| 2023 | SUDESTE |
| 2024 | SUDESTE |
| 2025 | SUDESTE |
| 2026 | SUDESTE/CENTRO-OESTE |

**Regra decidida:** usar `id_subsistema` como chave em qualquer join ou filtro,
nunca `nom_subsistema` — o nome mudou de `SUDESTE` para `SUDESTE/CENTRO-OESTE`
em 2026, mas o código `SE` não mudou em nenhum dos 12 anos (confirmado na tabela
acima).

---

## C. Cobertura temporal, por subsistema

| Subsistema | Primeiro instante | Último instante | Linhas | Timestamps distintos | Duplicados | Dias irregulares |
|---|---|---|---|---|---|---|
| N | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 | 101.112 | 101.112 | 0 | 1 |
| NE | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 | 101.136 | 101.136 | 0 | 0 |
| S | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 | 101.136 | 101.136 | 0 | 0 |
| SE | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 | 101.136 | 101.136 | 0 | 0 |

Dias irregulares (linhas != 24 registros), listados:

- N, 2015-04-09: 0 registros

---

## D. Horário de verão — os 9 timestamps especiais

Gerados por código: varredura hora a hora de 2015-01-01 a 2019-12-31 usando
`zoneinfo("America/Sao_Paulo")` (IANA tzdata) e `datetime.fold`, sem nenhuma data
hardcoded. Total de timestamps classificados como ambíguos ou inexistentes no
período: **9** (4 inexistentes + 5 ambíguos).

### Início de DST (timestamp local inexistente)

Valor vazio nos 4 subsistemas em 3 das 4 datas; na quarta (2018-11-04), 3
subsistemas vazios e 1 com notação científica (ver tabela e seção seguinte).

| Timestamp | N | NE | S | SE |
|---|---|---|---|---|
| 2015-10-18 00:00:00 | (vazio) | (vazio) | (vazio) | (vazio) |
| 2016-10-16 00:00:00 | (vazio) | (vazio) | (vazio) | (vazio) |
| 2017-10-15 00:00:00 | (vazio) | (vazio) | (vazio) | (vazio) |
| 2018-11-04 00:00:00 | (vazio) | (vazio) | 0E-8 | (vazio) |

### Fim de DST (timestamp local ambíguo — 1 hora física real não registrada)

| Timestamp | N | NE | S | SE |
|---|---|---|---|---|
| 2015-02-21 23:00:00 | 5305.46200000 | 10282.24062295 | 10469.39263063 | 39005.68200000 |
| 2016-02-20 23:00:00 | 5488.38199999 | 10247.31599999 | 10553.66499999 | 38682.99190371 |
| 2017-02-18 23:00:00 | 5511.73900000 | 11017.45100000 | 12021.52599999 | 40591.27800000 |
| 2018-02-17 23:00:00 | 5395.98799999 | 10638.50499999 | 10741.54899999 | 38062.88800000 |
| 2019-02-16 23:00:00 | 6091.62800000 | 11706.19400000 | 9974.35000000 | 35666.24099999 |

Os 9 timestamps, em ordem:

- 2015-02-21 23:00:00
- 2015-10-18 00:00:00
- 2016-02-20 23:00:00
- 2016-10-16 00:00:00
- 2017-02-18 23:00:00
- 2017-10-15 00:00:00
- 2018-02-17 23:00:00
- 2018-11-04 00:00:00
- 2019-02-16 23:00:00

### Notação científica na coluna string (anos 2015–2024)

| Subsistema | Timestamp | Valor bruto |
|---|---|---|
| S | 2018-11-04 | `0E-8` |

Total de ocorrências de notação científica na coluna inteira (2015-2024): 1.

---

## E. Anomalias conhecidas e não explicadas

| Subsistema | Valor mínimo | Timestamp do mínimo | Coincide com transição de DST? |
|---|---|---|---|
| N | 841,988 | 2018-03-21 16:00:00 | não |
| NE | 665,031 | 2018-03-21 16:00:00 | não |
| S | 0,000 | 2018-11-04 00:00:00 | sim |
| SE | 21.299,347 | 2015-06-28 07:00:00 | não |

**Aberto, sem explicação:** o mínimo histórico do subsistema NE (ver linha acima)
não coincide com nenhuma das 9 datas de transição de DST listadas na seção D.
Nenhuma causa foi investigada além dessa checagem de coincidência de data.

**2015-04-09, subsistema N:** 0 registros nesse dia
(dia inteiro ausente). Mesma data, outros subsistemas: NE=24, S=24, SE=24.

---

## F. Efeito do DST no perfil de carga (SE/CO, dez+jan, recalculado do zero)

Metodologia: mesma do relatório 03 — dezembro+janeiro de 4 verões com DST
(2015-16 a 2018-19) vs. 4 verões sem DST (2021-22 a 2024-25), os 9 timestamps da
seção D excluídos, dias úteis e fins de semana separados, com e sem normalização
por média diária.

| Regime | Tipo de dia | N dias |
|---|---|---|
| com_dst | dia_util | 176 |
| com_dst | fim_de_semana | 72 |
| sem_dst | dia_util | 177 |
| sem_dst | fim_de_semana | 71 |

| Regime | Tipo de dia | Base | Hora pico tarde | Hora pico noite | Razão noite/tarde |
|---|---|---|---|---|---|
| com_dst | dia_util | bruto | 15h | 21h | 0,9640 |
| com_dst | dia_util | normalizado | 15h | 21h | 0,9673 |
| com_dst | fim_de_semana | bruto | 17h | 20h | 1,1182 |
| com_dst | fim_de_semana | normalizado | 17h | 20h | 1,1198 |
| sem_dst | dia_util | bruto | 15h | 19h | 1,0194 |
| sem_dst | dia_util | normalizado | 15h | 19h | 1,0245 |
| sem_dst | fim_de_semana | bruto | 17h | 19h | 1,1050 |
| sem_dst | fim_de_semana | normalizado | 17h | 19h | 1,1077 |

**Limite declarado:** esta comparação NÃO isola o efeito do DST. Os grupos
diferem em ~7 anos de tendência de crescimento de carga, mudança de matriz
elétrica (geração solar distribuída cresceu no período) e efeitos pós-pandemia
sobre padrões de trabalho — nenhum desses confundidores foi controlado aqui.

---

## G. Temperatura — viabilidade

Fonte sem vazamento: Open-Meteo Previous Runs API
(`https://previous-runs-api.open-meteo.com/v1/forecast`,
`temperature_2m_previous_day1`), CC BY 4.0, sem chave.

### Cobertura inicial

Recalculada a partir dos arquivos de teste já baixados (não é uma nova
bisecção — nenhuma chamada de rede foi feita aqui). Duas definições distintas,
rotuladas separadamente — não são o mesmo fato:

| Janela | Primeiro timestamp não-nulo (fato bruto da fonte) | Primeiro dia com 24h completas, 0 nulos (derivado) | Horas disponíveis no dia do 1º timestamp não-nulo |
|---|---|---|---|
| mar2021 (São Paulo) | 2021-03-23T21:00 | 2021-03-24 | 3 de 24 |
| jan2024 (São Paulo) | 2024-01-19T09:00 | 2024-01-20 | 15 de 24 |

**Regra decidida:** o primeiro dia elegível como alvo de previsão day-ahead é
o primeiro dia com 24h completas (coluna 3 acima) — 2024-01-20 para a janela de
jan/2024. O dia anterior (2024-01-19) é parcial e utilizável apenas como
contexto/insumo, não como alvo de previsão.

### Previsão-24h vs. ERA5 (5 cidades, jan/2024–dez/2025)

| Cidade | N comparável | MAE | RMSE | Viés | MAE p95 | MAE p5 |
|---|---|---|---|---|---|---|
| Sao Paulo | 17.103 | 0,9935 | 1,3340 | 0,4060 | 0,9009 | 1,2300 |
| Rio de Janeiro | 17.103 | 1,1419 | 1,5425 | 0,2867 | 1,6744 | 1,2169 |
| Belo Horizonte | 17.103 | 1,0754 | 1,4139 | 0,4203 | 1,0793 | 1,2260 |
| Brasilia | 17.103 | 1,0565 | 1,3735 | 0,1228 | 0,9917 | 1,3483 |
| Goiania | 17.103 | 1,2837 | 1,6828 | 0,8090 | 0,8240 | 1,6951 |
| **Agregado** | 85.515 | **1,1102** | 1,4749 | 0,4090 | 1,1704 | 1,2233 |

MAE por hora — mínimo às 09h (0,8616), máximo às
19h (1,4240).

MAE no p95 (dias quentes) maior que o MAE geral em 2 de 5 cidades.
MAE no p5 (dias frios) maior que o MAE geral em 5 de 5 cidades.

### ERA5 vs. estação INMET A701 (São Paulo, 2024)

| Métrica | Valor |
|---|---|
| Linhas brutas da estação | 8.784 |
| Valores literais `9999` | 0 |
| Valores ausentes (total) | 19 |
| Horas comparáveis | 8.762 |
| Horas descartadas | 19 |
| MAE (ERA5 vs. estação) | 1,0194 |
| RMSE (ERA5 vs. estação) | 1,3557 |
| Viés (estação − ERA5) | 0,6205 |

**Nota:** ERA5 não é verdade absoluta — é uma reanálise, não uma medição
direta. Parte do erro atribuído à previsão-24h na seção anterior pode ser,
na verdade, divergência entre ERA5 e a realidade física medida em estação.
Os dois números (previsão-vs-ERA5 e ERA5-vs-estação) não são somáveis nem
diretamente comparáveis — comparam pares de séries diferentes.

---

## H. Decisões já tomadas

| Decisão | Justificativa |
|---|---|
| Alvo: SE/CO, carga horária | Maior subsistema, dado mais completo, foco do relatório 03 |
| Horizonte: day-ahead 24h | Alinhado ao lead time de `temperature_2m_previous_day1` |
| Eixo temporal: hora local (America/Sao_Paulo), sem conversão para UTC | Conversão para UTC introduz timestamps ambíguos/inexistentes sem ganho demonstrado (relatórios 01–02) |
| Janela: 2015–2026 | Todo o histórico disponível no portal do ONS no momento do snapshot |
| Viradas de DST: flag `is_dst_transition`, excluídas como origem de previsão; vazios de outubro NÃO imputados | Preserva o fato bruto em vez de mascará-lo com um valor inventado |
| Temperatura: camada secundária 2024+, não no modelo principal | Cobertura da previsão-24h só é completa a partir de 2024-01-20 (seção G) |
| Primeiro dia elegível como alvo de previsão day-ahead: 2024-01-20, não 2024-01-19 | 2024-01-19 tem cobertura parcial (ver seção G); dia parcial é contexto, não alvo |
| Custo de despacho: proxy via CMO/CVU do ONS | A verificar — não sondado ainda (ver seção I) |

---

## I. Itens abertos

- NE, mínimo histórico em 2018-03-21: sem explicação (seção E).
- CMO/CVU do ONS como proxy de custo de despacho: ainda não sondado.
- Datas de vigência do DST: confirmado nesta geração que são produzidas por
  `zoneinfo`/IANA dentro do próprio `src/gerar_facts.py`
  (função `gerar_timestamps_especiais_dst`), não hardcoded — ver seção D.

