# Sondagem — Curva de Carga Horária ONS (2015–2026)

Fase de sondagem do Projeto 3. Nenhuma limpeza, modelagem ou decisão foi feita.
Este documento reporta apenas fatos verificados diretamente nos arquivos brutos
baixados em `data/raw/`. Gerado em 2026-07-16.

Fonte: [ONS Open Data — Curva de Carga Horária](https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/curva-carga-ho/) (licença CC-BY).
Dicionário de dados de referência: versão 1.2, 06-04-2026.

---

## 1. Download e proveniência (MANIFEST.json)

Todos os 12 arquivos solicitados (2015–2026) existem no servidor e foram baixados com sucesso (HTTP 200). Nenhum 404.

| Arquivo | Tamanho (bytes) | SHA-256 | `Last-Modified` (servidor) | Baixado em (local, -03:00) |
|---|---|---|---|---|
| CURVA_CARGA_2015.parquet | 536.941 | `d1c5221ae4530faa...` | 2025-10-09 19:34:26 GMT | 2026-07-16T20:06:20-03:00 |
| CURVA_CARGA_2016.parquet | 507.019 | `3ac1e8d04a0163c0...` | 2025-10-09 19:34:54 GMT | 2026-07-16T20:06:22-03:00 |
| CURVA_CARGA_2017.parquet | 490.357 | `c2a9b40aed631dbe...` | 2025-10-09 19:35:18 GMT | 2026-07-16T20:06:24-03:00 |
| CURVA_CARGA_2018.parquet | 491.029 | `2bbea1ece1c05253...` | 2025-10-09 19:35:42 GMT | 2026-07-16T20:06:27-03:00 |
| CURVA_CARGA_2019.parquet | 491.284 | `bedba24a94859404...` | 2025-10-09 19:36:04 GMT | 2026-07-16T20:06:28-03:00 |
| CURVA_CARGA_2020.parquet | 492.028 | `f911806f72a63009...` | 2025-10-09 19:36:27 GMT | 2026-07-16T20:06:30-03:00 |
| CURVA_CARGA_2021.parquet | 492.643 | `016ed285452ca055...` | 2025-10-09 19:36:52 GMT | 2026-07-16T20:06:32-03:00 |
| CURVA_CARGA_2022.parquet | 498.130 | `670962bf091bc5e1...` | 2025-10-09 19:37:14 GMT | 2026-07-16T20:06:34-03:00 |
| CURVA_CARGA_2023.parquet | 492.541 | `d6f60c6c7b9df144...` | 2025-10-09 19:37:38 GMT | 2026-07-16T20:06:37-03:00 |
| CURVA_CARGA_2024.parquet | 489.394 | `aa1a74db69e36391...` | 2025-10-09 19:38:06 GMT | 2026-07-16T20:06:39-03:00 |
| CURVA_CARGA_2025.parquet | 383.346 | `e317f4c1a4b82f04...` | 2026-01-31 22:01:29 GMT | 2026-07-16T20:06:41-03:00 |
| CURVA_CARGA_2026.parquet | 213.700 | `f9ba7e7d56f0316a...` | 2026-07-16 22:00:56 GMT | 2026-07-16T20:06:42-03:00 |

Hashes completos, URLs e ETags: ver [`data/raw/MANIFEST.json`](../data/raw/MANIFEST.json).

**Fato observado:** os arquivos de 2015 a 2024 têm todos o mesmo `Last-Modified` de servidor,
09-10-2025, em sequência de segundos — indicando republicação em lote nessa data (consistente
com o "processo de consistência recorrente" do ONS mencionado no dicionário). O arquivo de 2025
foi modificado por último em 31-01-2026, e o de 2026 no próprio dia da consulta (16-07-2026, ano
corrente e ainda em andamento). Nenhuma comparação byte-a-byte contra uma versão anterior foi
feita — este é o primeiro snapshot deste projeto.

Re-execução do script de download confirmou que o mecanismo de verificação por hash funciona:
todos os 12 arquivos foram pulados na segunda chamada (hash local bateu com o manifesto).

---

## 2. Esquema, por ano

| Ano | Linhas | Colunas divergem do dicionário | `val_cargaenergiahomwmed` dtype real |
|---|---|---|---|
| 2015 | 35.016 | Nenhuma | `str` |
| 2016 | 35.136 | Nenhuma | `str` |
| 2017 | 35.040 | Nenhuma | `str` |
| 2018 | 35.040 | Nenhuma | `str` |
| 2019 | 35.040 | Nenhuma | `str` |
| 2020 | 35.136 | Nenhuma | `str` |
| 2021 | 35.040 | Nenhuma | `str` |
| 2022 | 35.040 | Nenhuma | `str` |
| 2023 | 35.040 | Nenhuma | `str` |
| 2024 | 35.136 | Nenhuma | `str` |
| 2025 | 35.040 | Nenhuma | `float64` |
| 2026 | 18.816 (parcial, até 15-07-2026) | Nenhuma | `float64` |

**Fato — nomes de coluna:** as 4 colunas do dicionário (`id_subsistema`, `nom_subsistema`,
`din_instante`, `val_cargaenergiahomwmed`) estão presentes em todos os 12 arquivos, sem coluna
extra ou faltante em nenhum ano.

**Fato — tipo de `val_cargaenergiahomwmed` diverge do dicionário:** o dicionário declara `FLOAT`.
Nos arquivos de 2015 a 2024 a coluna está armazenada como **texto** (`str`), com valores como
`"4865.85900000"` (separador decimal ponto, sem separador de milhar). Apenas 2025 e 2026 já vêm
como `float64`. Isso não foi corrigido — apenas reportado.

**Fato — `id_subsistema`/`nom_subsistema` dtype:** `str`/`object` em 2015–2025; em 2026 os arquivos
usam o tipo `string` (Arrow) do pandas em vez de `object` puro. Ambos representam texto; a
diferença é de representação interna do parquet, não de conteúdo.

### 2.1 Nulos (NaN real, via `isna()`)

Nenhuma das 4 colunas declaradas "não permite nulo" teve `NaN` em nenhum ano (0 em todos os 12 × 4
= 48 combinações ano/coluna). **Importante:** como `val_cargaenergiahomwmed` é texto em 2015–2024,
`isna()` não captura string vazia (`""`) — ver seção 2.2, essa é uma categoria de ausência
diferente de `NaN` e não seria pega por uma checagem de nulo ingênua.

### 2.2 Strings vazias em `val_cargaenergiahomwmed` (só ocorre nos anos em que a coluna é texto)

| Ano | Strings vazias | Não-parseável como número (excluindo vazias) |
|---|---|---|
| 2015 | 76 | 0 |
| 2016 | 4 | 0 |
| 2017 | 4 | 0 |
| 2018 | 3 | 0 |
| 2019–2024 | 0 | 0 |
| 2025–2026 | N/A (já é float) | N/A |

Total: 87 strings vazias em todo o período 2015–2026. Nenhum outro valor não-parseável foi
encontrado (todo valor não-vazio converteu para número).

### 2.3 Negativos e zeros em `val_cargaenergiahomwmed`

| Ano | Negativos | Zeros |
|---|---|---|
| 2015 | 0 | 0 |
| 2016 | 0 | 0 |
| 2017 | 0 | 0 |
| 2018 | 0 | **1** |
| 2019 | 0 | 0 |
| 2020 | 0 | 0 |
| 2021 | 0 | 0 |
| 2022 | 0 | 0 |
| 2023 | 0 | 0 |
| 2024 | 0 | 0 |
| 2025 | 0 | 0 |
| 2026 | 0 | 0 |

Nenhum valor negativo em nenhum ano (consistente com o dicionário). Um único zero, em 2018,
no subsistema S — ver seção 4 e 5 para o timestamp exato (2018-11-04 00:00:00).

### 2.4 Subsistemas — `id_subsistema` e `nom_subsistema`, por ano

Exatamente 4 códigos de subsistema em todos os 12 anos: `N`, `NE`, `S`, `SE`. Nenhum ano tem
menos ou mais de 4.

| Ano | `nom_subsistema` para `id_subsistema = "SE"` |
|---|---|
| 2015–2025 | `SUDESTE` |
| 2026 | `SUDESTE/CENTRO-OESTE` |

**Fato confirmado:** o nome do subsistema SE mudou de `SUDESTE` para `SUDESTE/CENTRO-OESTE` a
partir do arquivo de 2026 — consistente com a mudança de dicionário v1.2 citada no enunciado. O
**código** `id_subsistema` permaneceu `SE` em todos os anos, não mudou. Os demais 3 mapeamentos
(`N`→`NORTE`, `NE`→`NORDESTE`, `S`→`SUL`) não mudaram em nenhum ano do período baixado.

**Fato — comprimento observado vs. declarado:** o dicionário declara `id_subsistema` como TEXTO
de 3 posições; o comprimento observado em todos os anos é 1–2 caracteres (nunca 3). `nom_subsistema`
é declarado como TEXTO de 60 posições; o comprimento observado é 3–8 caracteres em 2015–2025 e
3–20 em 2026 (por causa de `SUDESTE/CENTRO-OESTE`). Nenhuma violação do limite máximo declarado
em nenhum dos dois casos.

---

## 3. Integridade temporal, por subsistema (período completo 2015-01-01 a 2026-07-15, todos os anos concatenados)

| Subsistema | Registros | Primeiro `din_instante` | Último `din_instante` | Timestamps duplicados | Horas esperadas | Horas observadas | Diferença |
|---|---|---|---|---|---|---|---|
| N | 101.112 | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 | 0 | 101.136 | 101.112 | **24 horas faltando** |
| NE | 101.136 | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 | 0 | 101.136 | 101.136 | 0 |
| S | 101.136 | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 | 0 | 101.136 | 101.136 | 0 |
| SE | 101.136 | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 | 0 | 101.136 | 101.136 | 0 |

Nenhum timestamp duplicado em nenhum subsistema, em nenhum ponto do período.

### 3.1 Dias sem exatamente 24 registros (lista completa)

De 4.214 dias no período, apenas **1 dia irregular** foi encontrado, e apenas em 1 subsistema:

| Subsistema | Dia | Registros observados |
|---|---|---|
| N | 2015-04-09 | **0** (dia inteiro ausente) |

NE, S e SE têm 4.214/4.214 dias com exatamente 24 registros — zero dias irregulares.

**Fato relevante para a nota sobre horário de verão:** o enunciado espera dias de 23h ou 25h em
2015–2019 por causa do horário de verão brasileiro (extinto a partir de 2019). **Isso não foi
observado nos dados** — nenhum dia de nenhum subsistema, em nenhum ano do período, tem 23 ou 25
registros. Todos os dias têm exatamente 24 registros, exceto o único caso de ausência total
(N, 2015-04-09, 0 registros). Ou seja: o arquivo aparenta já vir normalizado para grade horária
fixa de 24h/dia, sem refletir a transição de relógio na contagem de registros por dia — isso é
reportado como fato observado, não investigado a fundo (não é objetivo desta sondagem).

### 3.2 Maior sequência contígua sem buraco (passo de 1 hora)

| Subsistema | Tamanho (horas) | Início | Fim |
|---|---|---|---|
| N | 98.760 | 2015-04-10 00:00:00 | 2026-07-15 23:00:00 |
| NE | 101.136 (100% do período) | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 |
| S | 101.136 (100% do período) | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 |
| SE | 101.136 (100% do período) | 2015-01-01 00:00:00 | 2026-07-15 23:00:00 |

NE, S e SE são uma única sequência contígua sem nenhum buraco do início ao fim do período
baixado. N tem exatamente 1 quebra, correspondente ao dia ausente de 2015-04-09 (a sequência
recomeça em 2015-04-10 00:00:00 e segue contígua até o fim do período, 98.760 horas).

---

## 4. Descritivo bruto de `val_cargaenergiahomwmed`, por subsistema

Cálculo feito sobre os valores parseáveis como número (87 strings vazias em todo o período foram
excluídas do cálculo — ver seção 2.2 — não preenchidas nem interpoladas).

| Subsistema | N usados | N excluídos | Mín | Máx | Média | Mediana | Desvio padrão | Q1 (25%) | Q3 (75%) |
|---|---|---|---|---|---|---|---|---|---|
| N | 101.108 | 4 | 841,99 | 10.239,23 | 6.259,16 | 5.851,28 | 1.239,66 | 5.347,10 | 7.175,55 |
| NE | 101.108 | 28 | 665,03 | 18.156,97 | 11.216,75 | 11.075,45 | 1.685,92 | 10.026,01 | 12.291,60 |
| S | 101.109 | 27 | 0,00 | 22.737,44 | 11.896,37 | 11.911,24 | 2.605,40 | 9.905,44 | 13.594,17 |
| SE | 101.108 | 28 | 21.299,35 | 62.149,88 | 39.075,43 | 39.046,66 | 6.633,63 | 34.216,18 | 43.613,86 |

Unidade: MW médios (`val_cargaenergiahomwmed`), conforme dicionário.

### 4.1 Data e hora do máximo e do mínimo histórico, por subsistema

| Subsistema | Valor máximo | Data/hora do máximo | Valor mínimo | Data/hora do mínimo |
|---|---|---|---|---|
| N | 10.239,23 | 2025-11-17 15:00:00 | 841,99 | 2018-03-21 16:00:00 |
| NE | 18.156,97 | 2024-02-08 10:00:00 | 665,03 | 2018-03-21 16:00:00 |
| S | 22.737,44 | 2025-02-11 14:00:00 | 0,00 | 2018-11-04 00:00:00 |
| SE | 62.149,88 | 2025-02-18 14:00:00 | 21.299,35 | 2015-06-28 07:00:00 |

**Fato:** N e NE têm o mínimo histórico exatamente no mesmo timestamp — 2018-03-21 16:00:00.

**Fato:** o mínimo histórico do subsistema S (0,00) coincide com o único valor zero encontrado em
todo o dataset (seção 2.3), no timestamp 2018-11-04 00:00:00 — data que corresponde ao início do
horário de verão de 2018 no Brasil.

---

## 5. Gráficos exploratórios (SE/CO, sem conclusão)

Gerados em `reports/figures/`, a partir dos valores parseáveis (mesma base da seção 4, sem
tratamento de outlier):

| Arquivo | Conteúdo |
|---|---|
| [`a_serie_completa_2015_2026_seco.png`](figures/a_serie_completa_2015_2026_seco.png) | Série completa 2015–2026, SE/CO, média diária |
| [`b_perfil_horario_dia_semana_seco.png`](figures/b_perfil_horario_dia_semana_seco.png) | Perfil horário médio sobreposto: dia útil vs. sábado vs. domingo |
| [`c_perfil_horario_por_mes_seco.png`](figures/c_perfil_horario_por_mes_seco.png) | Perfil horário médio por mês (12 curvas) |
| [`d_recorte_pandemia_2020_seco.png`](figures/d_recorte_pandemia_2020_seco.png) | Março–dezembro de 2020, média diária |
| [`e_semana_tipica_2019_vs_2023_seco.png`](figures/e_semana_tipica_2019_vs_2023_seco.png) | Semana horária sobreposta: 06–13/05/2019 vs. 08–15/05/2023 |

As duas semanas do gráfico (e) foram escolhidas de forma fixa e determinística (primeira semana
completa de maio de cada ano, segunda a domingo, mês sem feriado nacional nem Carnaval/Corpus
Christi) — não há aleatoriedade envolvida, logo nenhuma seed foi necessária. Ambas as janelas
retornaram as 168 horas completas esperadas (7 dias × 24h), sem gaps.

---

## 6. Reprodutibilidade

- Ambiente: Python 3.12.10, dependências pinadas em [`requirements.txt`](../requirements.txt)
  (`pandas==3.0.3`, `pyarrow==25.0.0`, `matplotlib==3.11.0`, `numpy==2.5.1`, `requests==2.34.2`).
- Scripts, em ordem de execução: [`src/download_raw.py`](../src/download_raw.py) →
  [`src/probe_schema.py`](../src/probe_schema.py) → [`src/probe_temporal.py`](../src/probe_temporal.py) →
  [`src/probe_descriptive.py`](../src/probe_descriptive.py) → [`src/make_plots.py`](../src/make_plots.py).
- Saídas intermediárias em JSON (base numérica de todas as tabelas acima):
  [`data/interim/schema_probe.json`](../data/interim/schema_probe.json),
  [`data/interim/temporal_probe.json`](../data/interim/temporal_probe.json),
  [`data/interim/descriptive_probe.json`](../data/interim/descriptive_probe.json).
- Nenhuma aleatoriedade foi usada em nenhuma etapa desta sondagem.
