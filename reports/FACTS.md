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
- SHA-256 do `MANIFEST.json` neste momento: `655d2af507cdb6f582a52c7e05ecb86656f2db03ebf446e846a7dc8749c547fa`
- Total de entradas no manifesto (inclui arquivos de temperatura de sessões posteriores): 53

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

`val_cmo` (CMO Semi-Horário), dtype por ano — mesmo padrão de divergência de
tipo já observado em `val_cargaenergiahomwmed` acima, só que na direção oposta
(aqui o ano mais recente é o que vem como texto):

| Ano | dtype de `val_cmo` |
|---|---|
| 2024 | `float64` |
| 2025 | `float64` |
| 2026 | `str` |

Confirmado por `pd.to_numeric`: nenhum valor de 2026 falhou a conversão para número — não é corrupção de dado, só tipo declarado/armazenado divergente entre anos.

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

Estatística de valor (`val_cargaenergiahomwmed`), por subsistema, sobre os
valores válidos (NaN excluídos):

| Subsistema | N válidos | Mínimo | Timestamp mínimo | Máximo | Timestamp máximo | Média | Mediana | Desvio padrão | Q25 | Q75 |
|---|---|---|---|---|---|---|---|---|---|---|
| N | 101.108 | 841,988 | 2018-03-21 16:00:00 | 10.239,232 | 2025-11-17 15:00:00 | 6.259,163 | 5.851,278 | 1.239,663 | 5.347,105 | 7.175,555 |
| NE | 101.108 | 665,031 | 2018-03-21 16:00:00 | 18.156,972 | 2024-02-08 10:00:00 | 11.216,749 | 11.075,452 | 1.685,919 | 10.026,005 | 12.291,604 |
| S | 101.109 | 0,000 | 2018-11-04 00:00:00 | 22.737,443 | 2025-02-11 14:00:00 | 11.896,368 | 11.911,243 | 2.605,396 | 9.905,439 | 13.594,165 |
| SE | 101.108 | 21.299,347 | 2015-06-28 07:00:00 | 62.149,885 | 2025-02-18 14:00:00 | 39.075,430 | 39.046,664 | 6.633,629 | 34.216,183 | 43.613,862 |

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

**2015-04-09 — nenhum dos 4 subsistemas tem dado válido nesse dia,**
por duas formas distintas de ausência na mesma fonte:

| Subsistema | Linhas | Valores vazios | Forma de ausência |
|---|---|---|---|
| N | 0 | 0 | linha ausente |
| NE | 24 | 24 | linha presente, valor vazio |
| S | 24 | 24 | linha presente, valor vazio |
| SE | 24 | 24 | linha presente, valor vazio |

**Nota:** são duas formas distintas de ausência na mesma fonte. A forma
"linha presente, valor vazio" (NE, S, SE — 24 linhas, 24 valores vazios cada)
é a mesma observada nos 4 vazios de início de DST em outubro (seção D). A forma
"linha ausente" (N — 0 linhas) só ocorre nesta data.

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

## J. Custo de despacho

### J1. Fontes sondadas

Documentado a partir da página de cada dataset e do respectivo dicionário de
dados (não extraído do parquet — contexto fixo, como a licença na seção A):

| Dataset | URL | Licença | Anos disponíveis (portal) |
|---|---|---|---|
| CMO Semi-Horário | https://dados.ons.org.br/dataset/cmo-semi-horario | CC-BY | 2020–2026 |
| CMO Semanal | https://dados.ons.org.br/dataset/cmo-semanal | CC-BY | 2005–2026 |
| CVU das Usinas Térmicas | https://dados.ons.org.br/dataset/cvu-usitermica | CC-BY | 2005–2026 |

**Decisão tomada (registrada, não questionada aqui):** usar CMO Semi-Horário
como preço do erro de previsão, agregado para grade horária. CVU descartado
(exigiria modelar ordem de mérito). CMO Semanal descartado (granularidade
insuficiente).

### J2. Fato bruto vs. regra derivada — CMO Semi-Horário, amostra 2024

**Fato bruto — granularidade nativa:** diferença entre timestamps distintos
consecutivos é de 1.800 segundos (30 minutos)
na quase totalidade dos casos. Valores de diferença distintos observados no
arquivo inteiro: 1.800, 88.200 segundos.

**Fato bruto — subsistemas observados:** `N`, `NE`, `S`, `SE` —
4 subsistemas, mesmos códigos do dataset de carga.
Linhas por subsistema: N=17.376, NE=17.376, S=17.376, SE=17.376.

**Fato bruto — unidade:** R$/MWh, conforme dicionário de dados oficial
(`DicionarioDados_Cmo_Semi_Horario.pdf`).

**REGRA (decisão, não fato do dado):** para casar com a grade horária da
carga, os dois registros de 30 minutos de cada hora precisam ser agregados em
1 valor horário. O método de agregação (ex.: média das duas semi-horas) é uma
escolha de modelagem — **não foi aplicado nesta sondagem** e não está,
portanto, refletido em nenhum número desta seção.

### J3. Lacunas e anomalias — amostra 2024 (recalculado)

Período coberto pela amostra: `2024-01-01 00:00:00` a `2024-12-31 23:30:00`,
69.504 linhas totais.

Calendário de 366 dias no ano da amostra;
362 dias com pelo menos 1 registro por subsistema
(checado no subsistema SE). **4 dias inteiramente
ausentes**, gerados por código (calendário completo do ano menos dias
presentes):

- 2024-02-08
- 2024-02-17
- 2024-07-13
- 2024-12-29

Grade teoricamente completa (dias de calendário × 48 × 4 subsistemas):
70.272 linhas. Observado: 69.504.

**`val_cmo`, 69.504 valores válidos, 0 nulos:**
77 negativos, 8.989 zeros.

**Nota a registrar:** CMO zero e CMO negativo são fisicamente reais no SIN
(vertimento / sobra de energia) — não são erro de dado. Numa hora de CMO
zero, o custo do erro de previsão pela fórmula `|erro_MW| × CMO × 1h` também
é zero. Isso é consequência da suposição de precificação adotada (seção J5),
não um problema do dado.

### J4. Divergência de dicionário

O dicionário de dados do CMO Semanal declara `val_cmomediasemanal` em
**R$/MW**, enquanto as outras 3 colunas de valor do mesmo dataset
(`val_cmoleve`, `val_cmomedia`, `val_cmopesada`) são declaradas em
**R$/MWh** — mesmo dicionário, mesma tabela, unidades diferentes descritas
para colunas do mesmo tipo de grandeza. Registrado como está escrito no PDF
oficial; não investigado se é erro de digitação ou diferença real.

Este é o 3º caso, nesta sondagem, de o dicionário oficial do ONS divergir de
si mesmo ou dos dados: (1) seção B — coluna declarada `FLOAT` armazenada como
texto em 2015–2024; (2) seção B — 87 strings vazias numa coluna declarada
`Permite valor nulo: Não`; (3) esta.

### J5. Limite da métrica de custo — registrado literalmente

Nenhum dos três datasets sondados (CMO Semi-Horário, CMO Semanal, CVU)
contém uma ligação entre erro de carga (MW) e custo (R$) já calculada.
Nenhum contém o conceito de "erro de previsão". Os três contêm **preço**
(R$/MWh, ou R$/MW numa coluna — seção J4). A métrica de negócio do projeto
é, portanto, um **modelo declarado**, não um dado observado:

> custo = |erro_MW| × CMO_horário × 1h

sob a suposição de que o erro de previsão é valorado ao custo marginal de
operação do subsistema naquela hora. **Isto não é custo de despacho
realizado — é uma estimativa sob suposição explícita.**

### J6. Cobertura cruzada — carga SE/CO × CMO Semi-Horário

| Fonte | Período |
|---|---|
| Carga SE/CO (recalculado na seção C) | `2015-01-01 00:00:00` a `2026-07-15 23:00:00` |
| CMO Semi-Horário, amostra efetivamente baixada e verificada em detalhe nesta seção | `2024-01-01 00:00:00` a `2024-12-31 23:30:00` (ano 2024) |

Cobertura completa ano a ano (2020-2026), incluindo 2025-2026: seção J7.

### J7. Cobertura ano a ano do CMO Semi-Horário (2020-2026)

Auditoria completa dos anos em `data/raw/custo/` — não baixa nada, só audita
o que já está em disco. O período de avaliação do projeto usa só 2024+; os
anos abaixo cobrem a faixa que o **portal do ONS declara disponível**
(2020-2026), para que a afirmação de cobertura deixe de ser uma suposição.

| Ano | Arquivo | Linhas (SE) | Período no arquivo | Dias ausentes | Nulos | Negativos | Zeros | Min (R$/MWh) | Max (R$/MWh) |
|---|---|---|---|---|---|---|---|---|---|
| 2020 | ausente | — | — | — | — | — | — | — | — |
| 2021 | ausente | — | — | — | — | — | — | — | — |
| 2022 | ausente | — | — | — | — | — | — | — | — |
| 2023 | ausente | — | — | — | — | — | — | — | — |
| 2024 | presente (ano completo) | 17376 | `2024-01-01 00:00:00` a `2024-12-31 23:30:00` | 4 | 0 | 0 | 2211 | 0.0000 | 2126.0300 |
| 2025 | presente (ano completo) | 17472 | `2025-01-01 00:00:00` a `2025-12-31 23:30:00` | 1 | 0 | 3 | 1370 | -0.0800 | 2151.7000 |
| 2026 | presente (parcial (em andamento)) | 9552 | `2026-01-01 00:00:00` a `2026-07-20 23:30:00` | 2 | 0 | 0 | 938 | 0.0000 | 4870.9400 |

**4 ano(s) sem arquivo baixado: 2020, 2021, 2022, 2023.** Não é uma lacuna do projeto — o período de avaliação (`INICIO_AVALIACAO` = 2024-01-01) nunca precisou desses anos, então eles nunca foram baixados. A
cobertura 2020-2026 citada nos documentos é a listagem do portal (o que **pode**
ser baixado), não uma verificação de que os dados de 2020-2023 estão completos —
essa verificação não foi feita e não é necessária para os resultados do projeto.

**Buracos reais nos 3 anos efetivamente usados (2024, 2025, 2026):** nenhum
valor nulo, nenhum dia inteiramente ausente em 2020-2023 (não se aplica, ausentes)
— mas dias INDIVIDUAIS faltam dentro de cada ano presente:
- **2024:** 4 dia(s) sem nenhum registro de CMO: 2024-02-08, 2024-02-17, 2024-07-13, 2024-12-29.
- **2025:** 1 dia(s) sem nenhum registro de CMO: 2025-05-16.
- **2026:** 2 dia(s) sem nenhum registro de CMO: 2026-01-21, 2026-05-30.

O buraco de 2024 (4 dias) já constava em J3, recalculado aqui e batendo com o
valor anterior — confirma que o método é o mesmo. Os buracos de 2025 (1 dia) e
2026 (2 dias) são novos: nunca haviam sido checados em detalhe antes desta
auditoria. Nenhum dos três anos tem valor nulo, e a faixa de valores (mín/máx)
é plausível nos três, sem negativos extremos nem zeros fora do padrão já
registrado em J3/K2 — os buracos são dias sem registro nenhum, não valores
inválidos dentro de dias presentes.

---

## K. Agregação do CMO — sensibilidade e fuso (recalculado do zero)

### K1. Sensibilidade da métrica de custo à agregação do CMO (30min→60min)

Instrumento de medição: sazonal-naive (previsão(H,D) = observado(H,D−7)),
SE/CO, 2024, mesma metodologia da seção J (9 timestamps de `is_dst_transition`
— nenhum cai em 2024 —, 4 dias sem CMO excluídos da métrica de custo).

| Variante | Custo total (R$) | % do custo de (a) média |
|---|---|---|
| (a) Média das 2 semi-horas | 2.046.650.092,91 | 100,0000% |
| (b) Máximo das 2 semi-horas | 2.102.879.656,47 | 102,7474% |
| (c) Primeira semi-hora | 2.034.348.416,26 | 99,3989% |

Correlação entre séries horárias de custo: (a)×(b) = 0,993299,
(a)×(c) = 0,990839, (b)×(c) = 0,975031.

Horas em que (b) muda o custo em mais de 10% vs. (a): **586**
de 8.688. Horas em que (c) muda em mais de 10%: **586**.
Mesmo conjunto de horas nas duas comparações: sim.

**Regra decidida:** usar a média das duas semi-horas.

### K2. Efeito de CMO zero/negativo e concentração do custo

Valores semi-horários negativos no ano inteiro, **subsistema SE apenas**:
0. Não contradiz a seção J3 (77 negativos):
aquele número é a soma dos 4 subsistemas — os 77 negativos pertencem inteiramente
ao subsistema NE; SE não tem nenhum valor semi-horário negativo em 2024.
Horas com a MÉDIA horária do CMO igual a zero: 1.084.
Horas com a MÉDIA horária do CMO negativa: **0**.

Limiar do decil 90 do CMO médio horário: 359,8710 R$/MWh.
Horas nesse decil: 869.
% do custo total do ano (variante média) vindo dessas horas: **47,2269%**.

**Concentração de custo, período de avaliação 2024-01-01 a 2026-07-15 23:00:00 (naive semanal, régua principal — anos de CMO usados: 2024, 2025, 2026):** 25,2248% do custo nas 10% horas de CMO mais alto (2.208 de 22.080 horas com CMO; 168 de 22.248 horas totais sem CMO, excluídas só desta métrica). **O 47,2269% acima refere-se apenas a 2024 e não ao período de avaliação.**

### K3. Fuso horário do CMO — fatos brutos e fato derivado

Dicionários de dados verificados (CMO Semi-Horário e Curva de Carga) presentes
em `data/raw/documentacao/`: sim.
Nenhum dos dois menciona fuso horário, UTC ou hora local em nenhum lugar do
texto (verificado por leitura integral do PDF — relatório 07, seções 1-2).

Perfil intradiário do CMO (SE, 2024): pico às **18h** (171,0205 R$/MWh),
vale às **10h** (81,8598 R$/MWh).

Correlação entre o perfil horário do CMO e o perfil horário da carga SE/CO
(2024, rótulos de hora como armazenados, sem deslocamento): **0,4501**.
Correlação sob a hipótese "CMO está em UTC, corrigir +3h": **-0,0051**.

**FATO DERIVADO (não documentado pela fonte — síntese de evidência empírica,
não leitura de documentação):** o CMO Semi-Horário é tratado como hora local
(America/Sao_Paulo), mesma convenção da carga. Base: os três fatos brutos acima
convergem — sob a hipótese UTC, o perfil descreveria um sistema mais caro às
15h (hora local) que às 19h, e a correção de +3h destrói a correlação existente
(de 0,4501 para -0,0051) em vez de melhorá-la.

**Divergência registrada, não resolvida por omissão:** `reports/07_fuso_cmo.md`,
aplicando critério documental estrito (fuso só conta como determinado se
declarado pela fonte OU se o teste específico de deslocamento produzir um pico
nítido e isolado), concluiu **(c) o fuso permanece desconhecido** — o mesmo
teste de correlação, isoladamente, não teve um pico em ±3h que se distinguisse
com força do resto do ciclo de 24h testado (relatório 07, seção 1; relatório 06,
Parte A3). Esta seção registra uma leitura diferente do mesmo conjunto de fatos
— tratar os três fatos brutos como convergentes o suficiente para adotar hora
local como convenção de trabalho — sem apagar a conclusão (c) do relatório 07.
Confiança: alta por evidência (perfil físico + correlação), zero por
documentação (nenhuma fonte declara o fuso). Risco explícito: se o ONS
documentar o contrário, a métrica de custo precisa ser recalculada.

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
| Custo: CMO Semi-Horário agregado para grade horária pela MÉDIA das 2 semi-horas; CVU e CMO Semanal descartados | CVU exigiria modelar ordem de mérito; CMO Semanal tem granularidade insuficiente (seção J1); média testada contra máximo e primeira semi-hora, diferença de custo total pequena (seção K1) |
| Métrica de custo aplicada só ao período de teste (2020+), não ao treino | CMO Semi-Horário não cobre 2015–2019 (seção J1/J6) |
| Modelo principal (2015–2026) avaliado por MAPE/RMSE; custo é camada de avaliação, não de treino | Separa a qualidade estatística da previsão (todo o histórico) da tradução em custo (limitada pela cobertura do CMO) |
| Período de avaliação: inicia 2024-01-01, walk-forward day-ahead, origem deslizante usando todo o passado disponível, contexto >=2048h, tocado uma vez | Ver ESCOPO.md seção Validação |

---

## I. Itens abertos

- NE, mínimo histórico em 2018-03-21: sem explicação (seção E).
- Cobertura do CMO Semi-Horário para 2020-2023 não confirmada — nunca baixados
  porque a avaliação (2024-01-01+) nunca precisou deles; 2024-2026 (os anos
  usados) já verificados ano a ano (seção J7).
- Fuso do CMO Semi-Horário: fato derivado por evidência empírica (seção K3),
  não declarado por nenhuma fonte documental — risco permanece se o ONS
  documentar o contrário no futuro.
- Datas de vigência do DST: confirmado nesta geração que são produzidas por
  `zoneinfo`/IANA dentro do próprio `src/gerar_facts.py`
  (função `gerar_timestamps_especiais_dst`), não hardcoded — ver seção D.

---

## L. Custo assimétrico (ESCOPO.md seção 12f)

Única seção deste documento que depende de previsões de modelo já salvas em
`data/processed/` (via `src/custo_assimetrico.py`), não só de `data/raw/` — as
seções A-K acima são fatos puros de dado bruto. Subprevisão (previsto < real)
custa `fator_sub` vezes mais que superprevisão, ao preço marginal (CMO).
`fator_sub=1.0` é o controle: reproduz o custo simétrico já comprometido em
`reports/tabela_comparativa.csv` — conferido automaticamente antes desta seção
ser escrita (o script inteiro aborta se divergir).

### L1. Sensibilidade: custo total por modelo × fator_sub

| Modelo | 1.0× | 1.5× | 2.0× | 3.0× |
|---|---|---|---|---|
| naive semanal | R$ 8.52 bi | R$ 10.74 bi | R$ 12.97 bi | R$ 17.43 bi |
| SARIMA | R$ 8.40 bi | R$ 11.07 bi | R$ 13.73 bi | R$ 19.05 bi |
| Prophet | R$ 7.86 bi | R$ 10.15 bi | R$ 12.45 bi | R$ 17.03 bi |
| Chronos-2 | R$ 3.01 bi | R$ 3.86 bi | R$ 4.72 bi | R$ 6.43 bi |

### L2. Viés direcional — % do erro absoluto vindo de sub vs. super

| Modelo | Horas subprevisão | Horas superprevisão | % erro de subprevisão | % erro de superprevisão |
|---|---|---|---|---|
| naive semanal | 11168 | 10912 | 49.77% | 50.23% |
| SARIMA | 12656 | 9424 | 51.81% | 48.19% |
| Prophet | 11054 | 11026 | 49.53% | 50.47% |
| Chronos-2 | 11669 | 10411 | 51.83% | 48.17% |

Um modelo bem calibrado fica perto de 50/50. Acima de 50% em subprevisão é o
viés operacionalmente perigoso — é a direção que o custo assimétrico (L1)
penaliza mais.

### L3. Robustez do ranking por custo

- `fator_sub=1.0`: Chronos-2 > Prophet > SARIMA > naive semanal (melhor → pior)
- `fator_sub=1.5`: Chronos-2 > Prophet > naive semanal > SARIMA (melhor → pior)
- `fator_sub=2.0`: Chronos-2 > Prophet > naive semanal > SARIMA (melhor → pior)
- `fator_sub=3.0`: Chronos-2 > Prophet > naive semanal > SARIMA (melhor → pior)

**Ranking NÃO robusto:** muda de `fator_sub=1.0` para fatores maiores — os modelos com maior viés de subprevisão (L2) pioram de posição relativa conforme `fator_sub` cresce (ver tabela acima).
Vencedor em `fator_sub=1.0`: **Chronos-2**. Vencedor em `fator_sub=3.0`: **Chronos-2** — o mesmo modelo, mesmo sob o custo assimétrico mais extremo testado.

**Limitação declarada, não modelada:** VOLL (*Value of Lost Load*, ~US$10.000/MWh
em mercados como o MISO — ordens de magnitude acima do CMO típico) não entra em
nenhum fator_sub acima. Aplica-se só às horas de corte de carga efetivo, que este
dataset não identifica (ESCOPO.md seção 16).

Gráfico: `reports/figures/resultado_8_custo_assimetrico.png`. Tabelas completas:
`reports/tabela_custo_assimetrico.csv`, `reports/tabela_vies_direcional.csv`.

