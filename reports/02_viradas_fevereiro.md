# Explicação do buraco de 3 horas em UTC nas viradas de fim de DST

Fase de sondagem do Projeto 3. Nenhuma limpeza, correção ou decisão foi feita.
Este documento explica um fato específico do relatório anterior
(`reports/01_dst_verificacao.md`, seção 6.3) e reporta apenas o que os dados mostram,
inclusive onde não explicam algo. Gerado em 2026-07-16.

**Fato a explicar:** a conversão de `din_instante` do SE/CO para UTC produziu, em cada
uma das 5 viradas de fim de DST (fevereiro), uma diferença de 3,0 horas entre o último
timestamp UTC antes do buraco e o primeiro depois — maior que a 1 hora que o recuo de
relógio, por si só, produziria.

---

## 1. Janela bruta completa (sábado 20:00 até domingo 06:00), N e SE/CO lado a lado

Valor bruto exatamente como armazenado no arquivo original (string, anos 2015–2019 —
nenhuma conversão aplicada aqui).

#### Virada 2015-02-21 / 2015-02-22

| din_instante | N (bruto) | SE (bruto) |
|---|---|---|
| 2015-02-21 20:00:00 | 5397.57900000 | 43241.11900000 |
| 2015-02-21 21:00:00 | 5422.41699999 | 42251.97999999 |
| 2015-02-21 22:00:00 | 5363.62800000 | 40505.12799999 |
| 2015-02-21 23:00:00 | 5305.46200000 | 39005.68200000 |
| 2015-02-22 00:00:00 | 5028.57599999 | 35225.08500000 |
| 2015-02-22 01:00:00 | 4933.82499999 | 33654.90399999 |
| 2015-02-22 02:00:00 | 4834.76999999 | 32616.21099999 |
| 2015-02-22 03:00:00 | 4780.18200000 | 31861.61100000 |
| 2015-02-22 04:00:00 | 4714.18699999 | 31407.99300000 |
| 2015-02-22 05:00:00 | 4600.17100000 | 30891.48199999 |
| 2015-02-22 06:00:00 | 4371.58800000 | 29358.80000000 |

#### Virada 2016-02-20 / 2016-02-21

| din_instante | N (bruto) | SE (bruto) |
|---|---|---|
| 2016-02-20 20:00:00 | 5456.71800000 | 42173.72519253 |
| 2016-02-20 21:00:00 | 5511.12800000 | 41410.02701297 |
| 2016-02-20 22:00:00 | 5500.47700000 | 40092.79322278 |
| 2016-02-20 23:00:00 | 5488.38199999 | 38682.99190371 |
| 2016-02-21 00:00:00 | 5379.05800000 | 35283.89411053 |
| 2016-02-21 01:00:00 | 5284.57200000 | 33890.11711861 |
| 2016-02-21 02:00:00 | 5207.39200000 | 32731.17632146 |
| 2016-02-21 03:00:00 | 5115.66100000 | 31947.65630803 |
| 2016-02-21 04:00:00 | 5011.49100000 | 31489.26286448 |
| 2016-02-21 05:00:00 | 4925.39700000 | 30986.13057151 |
| 2016-02-21 06:00:00 | 4653.71000000 | 29552.08095826 |

#### Virada 2017-02-18 / 2017-02-19

| din_instante | N (bruto) | SE (bruto) |
|---|---|---|
| 2017-02-18 20:00:00 | 5462.54500000 | 44120.16000000 |
| 2017-02-18 21:00:00 | 5526.77600000 | 43372.09099999 |
| 2017-02-18 22:00:00 | 5550.46400000 | 41857.46799999 |
| 2017-02-18 23:00:00 | 5511.73900000 | 40591.27800000 |
| 2017-02-19 00:00:00 | 5386.50400000 | 37114.82099999 |
| 2017-02-19 01:00:00 | 5264.86599999 | 35919.08600000 |
| 2017-02-19 02:00:00 | 5161.25399999 | 34743.88300000 |
| 2017-02-19 03:00:00 | 5051.82100000 | 33659.37599999 |
| 2017-02-19 04:00:00 | 4919.34599999 | 33272.65900000 |
| 2017-02-19 05:00:00 | 4841.20499999 | 32728.03099999 |
| 2017-02-19 06:00:00 | 4661.71400000 | 31240.15400000 |

#### Virada 2018-02-17 / 2018-02-18

| din_instante | N (bruto) | SE (bruto) |
|---|---|---|
| 2018-02-17 20:00:00 | 5688.55500000 | 42601.55800000 |
| 2018-02-17 21:00:00 | 5697.52200000 | 41268.44300000 |
| 2018-02-17 22:00:00 | 5651.26700000 | 39512.09800000 |
| 2018-02-17 23:00:00 | 5395.98799999 | 38062.88800000 |
| 2018-02-18 00:00:00 | 5424.12200000 | 33961.88200000 |
| 2018-02-18 01:00:00 | 5370.02799999 | 32574.17099999 |
| 2018-02-18 02:00:00 | 5299.38300000 | 31642.23399999 |
| 2018-02-18 03:00:00 | 5235.50200000 | 30995.70800000 |
| 2018-02-18 04:00:00 | 5185.87599999 | 30532.53399999 |
| 2018-02-18 05:00:00 | 5053.87500000 | 30139.55699999 |
| 2018-02-18 06:00:00 | 4871.87299999 | 29213.07299999 |

#### Virada 2019-02-16 / 2019-02-17

| din_instante | N (bruto) | SE (bruto) |
|---|---|---|
| 2019-02-16 20:00:00 | 6042.83999999 | 40775.96700000 |
| 2019-02-16 21:00:00 | 6107.33600000 | 39636.48800000 |
| 2019-02-16 22:00:00 | 6106.79700000 | 37579.65600000 |
| 2019-02-16 23:00:00 | 6091.62800000 | 35666.24099999 |
| 2019-02-17 00:00:00 | 5803.38799999 | 32483.15700000 |
| 2019-02-17 01:00:00 | 5659.10999999 | 31329.84600000 |
| 2019-02-17 02:00:00 | 5544.09500000 | 30337.78100000 |
| 2019-02-17 03:00:00 | 5403.50800000 | 29841.85200000 |
| 2019-02-17 04:00:00 | 5284.92800000 | 29619.09199999 |
| 2019-02-17 05:00:00 | 5154.66199999 | 29369.44400000 |
| 2019-02-17 06:00:00 | 4858.38200000 | 28434.89500000 |

Em todas as 5 janelas, N e SE têm exatamente 11 linhas cada, uma por hora, sem lacuna e
sem valor vazio (diferente do padrão de outubro/novembro reportado em
`reports/01_dst_verificacao.md` seção 3.1).

---

## 2. Conversão para UTC, linha a linha (SE/CO), com classificação

Conversão feita via `zoneinfo("America/Sao_Paulo")` e `datetime.fold`, checando para
cada linha se o horário local tem uma única correspondência UTC (fold=0 e fold=1 dão o
mesmo resultado) ou duas correspondências diferentes (fold=0 ≠ fold=1 → ambíguo).

#### Virada 2015-02-21 / 2015-02-22

| din_instante (local) | SE (bruto) | Conversão UTC | Classificação |
|---|---|---|---|
| 2015-02-21 20:00:00 | 43241.11900000 | 2015-02-21 22:00:00+00:00 | ok |
| 2015-02-21 21:00:00 | 42251.97999999 | 2015-02-21 23:00:00+00:00 | ok |
| 2015-02-21 22:00:00 | 40505.12799999 | 2015-02-22 00:00:00+00:00 | ok |
| 2015-02-21 23:00:00 | 39005.68200000 | fold0=2015-02-22 01:00:00+00:00 \| fold1=2015-02-22 02:00:00+00:00 | **AMBÍGUO** |
| 2015-02-22 00:00:00 | 35225.08500000 | 2015-02-22 03:00:00+00:00 | ok |
| 2015-02-22 01:00:00 | 33654.90399999 | 2015-02-22 04:00:00+00:00 | ok |
| 2015-02-22 02:00:00 | 32616.21099999 | 2015-02-22 05:00:00+00:00 | ok |
| 2015-02-22 03:00:00 | 31861.61100000 | 2015-02-22 06:00:00+00:00 | ok |
| 2015-02-22 04:00:00 | 31407.99300000 | 2015-02-22 07:00:00+00:00 | ok |
| 2015-02-22 05:00:00 | 30891.48199999 | 2015-02-22 08:00:00+00:00 | ok |
| 2015-02-22 06:00:00 | 29358.80000000 | 2015-02-22 09:00:00+00:00 | ok |

#### Virada 2016-02-20 / 2016-02-21

| din_instante (local) | SE (bruto) | Conversão UTC | Classificação |
|---|---|---|---|
| 2016-02-20 20:00:00 | 42173.72519253 | 2016-02-20 22:00:00+00:00 | ok |
| 2016-02-20 21:00:00 | 41410.02701297 | 2016-02-20 23:00:00+00:00 | ok |
| 2016-02-20 22:00:00 | 40092.79322278 | 2016-02-21 00:00:00+00:00 | ok |
| 2016-02-20 23:00:00 | 38682.99190371 | fold0=2016-02-21 01:00:00+00:00 \| fold1=2016-02-21 02:00:00+00:00 | **AMBÍGUO** |
| 2016-02-21 00:00:00 | 35283.89411053 | 2016-02-21 03:00:00+00:00 | ok |
| 2016-02-21 01:00:00 | 33890.11711861 | 2016-02-21 04:00:00+00:00 | ok |
| 2016-02-21 02:00:00 | 32731.17632146 | 2016-02-21 05:00:00+00:00 | ok |
| 2016-02-21 03:00:00 | 31947.65630803 | 2016-02-21 06:00:00+00:00 | ok |
| 2016-02-21 04:00:00 | 31489.26286448 | 2016-02-21 07:00:00+00:00 | ok |
| 2016-02-21 05:00:00 | 30986.13057151 | 2016-02-21 08:00:00+00:00 | ok |
| 2016-02-21 06:00:00 | 29552.08095826 | 2016-02-21 09:00:00+00:00 | ok |

#### Virada 2017-02-18 / 2017-02-19

| din_instante (local) | SE (bruto) | Conversão UTC | Classificação |
|---|---|---|---|
| 2017-02-18 20:00:00 | 44120.16000000 | 2017-02-18 22:00:00+00:00 | ok |
| 2017-02-18 21:00:00 | 43372.09099999 | 2017-02-18 23:00:00+00:00 | ok |
| 2017-02-18 22:00:00 | 41857.46799999 | 2017-02-19 00:00:00+00:00 | ok |
| 2017-02-18 23:00:00 | 40591.27800000 | fold0=2017-02-19 01:00:00+00:00 \| fold1=2017-02-19 02:00:00+00:00 | **AMBÍGUO** |
| 2017-02-19 00:00:00 | 37114.82099999 | 2017-02-19 03:00:00+00:00 | ok |
| 2017-02-19 01:00:00 | 35919.08600000 | 2017-02-19 04:00:00+00:00 | ok |
| 2017-02-19 02:00:00 | 34743.88300000 | 2017-02-19 05:00:00+00:00 | ok |
| 2017-02-19 03:00:00 | 33659.37599999 | 2017-02-19 06:00:00+00:00 | ok |
| 2017-02-19 04:00:00 | 33272.65900000 | 2017-02-19 07:00:00+00:00 | ok |
| 2017-02-19 05:00:00 | 32728.03099999 | 2017-02-19 08:00:00+00:00 | ok |
| 2017-02-19 06:00:00 | 31240.15400000 | 2017-02-19 09:00:00+00:00 | ok |

#### Virada 2018-02-17 / 2018-02-18

| din_instante (local) | SE (bruto) | Conversão UTC | Classificação |
|---|---|---|---|
| 2018-02-17 20:00:00 | 42601.55800000 | 2018-02-17 22:00:00+00:00 | ok |
| 2018-02-17 21:00:00 | 41268.44300000 | 2018-02-17 23:00:00+00:00 | ok |
| 2018-02-17 22:00:00 | 39512.09800000 | 2018-02-18 00:00:00+00:00 | ok |
| 2018-02-17 23:00:00 | 38062.88800000 | fold0=2018-02-18 01:00:00+00:00 \| fold1=2018-02-18 02:00:00+00:00 | **AMBÍGUO** |
| 2018-02-18 00:00:00 | 33961.88200000 | 2018-02-18 03:00:00+00:00 | ok |
| 2018-02-18 01:00:00 | 32574.17099999 | 2018-02-18 04:00:00+00:00 | ok |
| 2018-02-18 02:00:00 | 31642.23399999 | 2018-02-18 05:00:00+00:00 | ok |
| 2018-02-18 03:00:00 | 30995.70800000 | 2018-02-18 06:00:00+00:00 | ok |
| 2018-02-18 04:00:00 | 30532.53399999 | 2018-02-18 07:00:00+00:00 | ok |
| 2018-02-18 05:00:00 | 30139.55699999 | 2018-02-18 08:00:00+00:00 | ok |
| 2018-02-18 06:00:00 | 29213.07299999 | 2018-02-18 09:00:00+00:00 | ok |

#### Virada 2019-02-16 / 2019-02-17

| din_instante (local) | SE (bruto) | Conversão UTC | Classificação |
|---|---|---|---|
| 2019-02-16 20:00:00 | 40775.96700000 | 2019-02-16 22:00:00+00:00 | ok |
| 2019-02-16 21:00:00 | 39636.48800000 | 2019-02-16 23:00:00+00:00 | ok |
| 2019-02-16 22:00:00 | 37579.65600000 | 2019-02-17 00:00:00+00:00 | ok |
| 2019-02-16 23:00:00 | 35666.24099999 | fold0=2019-02-17 01:00:00+00:00 \| fold1=2019-02-17 02:00:00+00:00 | **AMBÍGUO** |
| 2019-02-17 00:00:00 | 32483.15700000 | 2019-02-17 03:00:00+00:00 | ok |
| 2019-02-17 01:00:00 | 31329.84600000 | 2019-02-17 04:00:00+00:00 | ok |
| 2019-02-17 02:00:00 | 30337.78100000 | 2019-02-17 05:00:00+00:00 | ok |
| 2019-02-17 03:00:00 | 29841.85200000 | 2019-02-17 06:00:00+00:00 | ok |
| 2019-02-17 04:00:00 | 29619.09199999 | 2019-02-17 07:00:00+00:00 | ok |
| 2019-02-17 05:00:00 | 29369.44400000 | 2019-02-17 08:00:00+00:00 | ok |
| 2019-02-17 06:00:00 | 28434.89500000 | 2019-02-17 09:00:00+00:00 | ok |

Nas 5 janelas, exatamente 1 linha é classificada como AMBÍGUA (sempre a hora local
23:00 do sábado) e nenhuma linha é classificada como INEXISTENTE (nenhuma hora
inexistente ocorre nas janelas de fevereiro — isso só ocorre nas de outubro/novembro,
ver `reports/01_dst_verificacao.md` seções 3.1 e 6.1). As outras 10 linhas de cada
janela convertem para um único valor UTC (fold=0 e fold=1 concordam).

---

## 3. Instantes UTC ausentes, um a um

Usando o mesmo método do relatório 01 (`ambiguous="raise"`, `nonexistent="raise"`, a
linha ambígua é descartada e não gera nenhum valor UTC), o último UTC antes do buraco e
o primeiro UTC depois, por virada:

| Virada | Último UTC antes do buraco | Primeiro UTC depois do buraco | Instantes UTC ausentes (listados) | Quantidade de instantes ausentes |
|---|---|---|---|---|
| 2015-02-21/22 | 2015-02-22 00:00:00+00:00 | 2015-02-22 03:00:00+00:00 | 2015-02-22 01:00:00+00:00; 2015-02-22 02:00:00+00:00 | 2 |
| 2016-02-20/21 | 2016-02-21 00:00:00+00:00 | 2016-02-21 03:00:00+00:00 | 2016-02-21 01:00:00+00:00; 2016-02-21 02:00:00+00:00 | 2 |
| 2017-02-18/19 | 2017-02-19 00:00:00+00:00 | 2017-02-19 03:00:00+00:00 | 2017-02-19 01:00:00+00:00; 2017-02-19 02:00:00+00:00 | 2 |
| 2018-02-17/18 | 2018-02-18 00:00:00+00:00 | 2018-02-18 03:00:00+00:00 | 2018-02-18 01:00:00+00:00; 2018-02-18 02:00:00+00:00 | 2 |
| 2019-02-16/17 | 2019-02-17 00:00:00+00:00 | 2019-02-17 03:00:00+00:00 | 2019-02-17 01:00:00+00:00; 2019-02-17 02:00:00+00:00 | 2 |

O número de instantes UTC efetivamente ausentes é **2** em cada virada (não 3). O valor
de 3,0 relatado em `reports/01_dst_verificacao.md` seção 6.3 é a diferença em horas
entre o timestamp anterior e o posterior ao buraco (`03:00 − 00:00 = 3`), o que
corresponde a 2 posições intermediárias vazias na grade de 1 em 1 hora (01:00 e 02:00),
não a 3 instantes ausentes.

Os 2 instantes ausentes em cada virada coincidem exatamente com os 2 candidatos UTC
gerados pela hora local ambígua sob `fold=0` e `fold=1` (seção 2): a linha local única
`sábado 23:00` corresponderia, em tempo físico real, a dois instantes UTC distintos
(`fold=0` e `fold=1`), e nenhum dos dois aparece na conversão porque a linha inteira é
descartada quando classificada como ambígua sob a política `raise`.

---

## 4. Hipótese "hora repetida foi somada" — valor observado vs. média de referência (SE/CO)

Referência: mesmo subsistema, mesmo rótulo de hora, nos mesmos dias da semana 7, 14 e 21
dias antes e 7, 14 e 21 dias depois da data de cada ponto (6 valores de referência por
ponto).

#### Virada 2015-02-21/22

| Ponto | din_instante | Valor observado | Média de referência (6 pontos) | Razão observado / referência |
|---|---|---|---|---|
| sáb 21:00 | 2015-02-21 21:00:00 | 42251,98 | 40215,16 | 1,0506 |
| sáb 22:00 | 2015-02-21 22:00:00 | 40505,13 | 38332,70 | 1,0567 |
| **sáb 23:00 (AMBÍGUA)** | 2015-02-21 23:00:00 | 39005,68 | 36668,26 | **1,0637** |
| dom 00:00 | 2015-02-22 00:00:00 | 35225,09 | 34631,16 | 1,0172 |
| dom 01:00 | 2015-02-22 01:00:00 | 33654,90 | 32858,28 | 1,0242 |
| dom 02:00 | 2015-02-22 02:00:00 | 32616,21 | 31511,54 | 1,0351 |

#### Virada 2016-02-20/21

| Ponto | din_instante | Valor observado | Média de referência (6 pontos) | Razão observado / referência |
|---|---|---|---|---|
| sáb 21:00 | 2016-02-20 21:00:00 | 41410,03 | 40288,59 | 1,0278 |
| sáb 22:00 | 2016-02-20 22:00:00 | 40092,79 | 38637,93 | 1,0377 |
| **sáb 23:00 (AMBÍGUA)** | 2016-02-20 23:00:00 | 38682,99 | 37166,17 | **1,0408** |
| dom 00:00 | 2016-02-21 00:00:00 | 35283,89 | 35204,43 | 1,0023 |
| dom 01:00 | 2016-02-21 01:00:00 | 33890,12 | 33370,36 | 1,0156 |
| dom 02:00 | 2016-02-21 02:00:00 | 32731,18 | 32039,99 | 1,0216 |

#### Virada 2017-02-18/19

| Ponto | din_instante | Valor observado | Média de referência (6 pontos) | Razão observado / referência |
|---|---|---|---|---|
| sáb 21:00 | 2017-02-18 21:00:00 | 43372,09 | 41300,94 | 1,0501 |
| sáb 22:00 | 2017-02-18 22:00:00 | 41857,47 | 39750,69 | 1,0530 |
| **sáb 23:00 (AMBÍGUA)** | 2017-02-18 23:00:00 | 40591,28 | 38205,46 | **1,0624** |
| dom 00:00 | 2017-02-19 00:00:00 | 37114,82 | 36364,78 | 1,0206 |
| dom 01:00 | 2017-02-19 01:00:00 | 35919,09 | 34663,44 | 1,0362 |
| dom 02:00 | 2017-02-19 02:00:00 | 34743,88 | 33379,80 | 1,0409 |

#### Virada 2018-02-17/18

| Ponto | din_instante | Valor observado | Média de referência (6 pontos) | Razão observado / referência |
|---|---|---|---|---|
| sáb 21:00 | 2018-02-17 21:00:00 | 41268,44 | 40461,09 | 1,0200 |
| sáb 22:00 | 2018-02-17 22:00:00 | 39512,10 | 38788,72 | 1,0186 |
| **sáb 23:00 (AMBÍGUA)** | 2018-02-17 23:00:00 | 38062,89 | 37127,00 | **1,0252** |
| dom 00:00 | 2018-02-18 00:00:00 | 33961,88 | 35128,03 | 0,9668 |
| dom 01:00 | 2018-02-18 01:00:00 | 32574,17 | 33367,88 | 0,9762 |
| dom 02:00 | 2018-02-18 02:00:00 | 31642,23 | 32148,64 | 0,9842 |

#### Virada 2019-02-16/17

| Ponto | din_instante | Valor observado | Média de referência (6 pontos) | Razão observado / referência |
|---|---|---|---|---|
| sáb 21:00 | 2019-02-16 21:00:00 | 39636,49 | 42704,28 | 0,9282 |
| sáb 22:00 | 2019-02-16 22:00:00 | 37579,66 | 41216,81 | 0,9118 |
| **sáb 23:00 (AMBÍGUA)** | 2019-02-16 23:00:00 | 35666,24 | 39731,68 | **0,8977** |
| dom 00:00 | 2019-02-17 00:00:00 | 32483,16 | 37754,67 | 0,8604 |
| dom 01:00 | 2019-02-17 01:00:00 | 31329,85 | 36191,23 | 0,8657 |
| dom 02:00 | 2019-02-17 02:00:00 | 30337,78 | 34831,95 | 0,8710 |

Faixa completa de razões observadas nas 5 viradas × 6 pontos (30 valores): 0,8604 a
1,0637. A razão do ponto "sáb 23:00 (ambígua)" especificamente, nas 5 viradas: 1,0637;
1,0408; 1,0624; 1,0252; 0,8977 — nenhuma dessas 5 razões está próxima de 2. Nenhuma das
30 razões calculadas (ambíguo ou vizinhos) está próxima de 2.

---

## 5. Métodos alternativos de conversão UTC (SE/CO completo, 101.136 linhas, 2015–2026)

| Método | Linhas | Timestamps UTC distintos | Duplicatas |
|---|---|---|---|
| `fold=0` | 101.136 | 101.132 | 4 |
| `fold=1` | 101.136 | 101.132 | 4 |
| offset fixo UTC−3 (sem DST) | 101.136 | 101.136 | 0 |
| offset fixo UTC−2 (sem DST) | 101.136 | 101.136 | 0 |

Nenhum dos 4 métodos gera erro (diferente do método `raise` usado no relatório 01) —
`fold=0` e `fold=1` resolvem toda hora ambígua ou inexistente para um valor UTC único
sem descartar linha, e os offsets fixos não têm noção de ambiguidade ou inexistência.

Detalhamento das 4 duplicatas de `fold=0` (dois `din_instante` locais diferentes
mapeando para o mesmo UTC):

| UTC duplicado | Origens locais |
|---|---|
| 2015-10-18 03:00:00+00:00 | 2015-10-18 00:00:00 e 2015-10-18 01:00:00 |
| 2016-10-16 03:00:00+00:00 | 2016-10-16 00:00:00 e 2016-10-16 01:00:00 |
| 2017-10-15 03:00:00+00:00 | 2017-10-15 00:00:00 e 2017-10-15 01:00:00 |
| 2018-11-04 03:00:00+00:00 | 2018-11-04 00:00:00 e 2018-11-04 01:00:00 |

Detalhamento das 4 duplicatas de `fold=1`:

| UTC duplicado | Origens locais |
|---|---|
| 2015-10-18 02:00:00+00:00 | 2015-10-17 23:00:00 e 2015-10-18 00:00:00 |
| 2016-10-16 02:00:00+00:00 | 2016-10-15 23:00:00 e 2016-10-16 00:00:00 |
| 2017-10-15 02:00:00+00:00 | 2017-10-14 23:00:00 e 2017-10-15 00:00:00 |
| 2018-11-04 02:00:00+00:00 | 2018-11-03 23:00:00 e 2018-11-04 00:00:00 |

As 4 duplicatas de `fold=0` e as 4 de `fold=1` ocorrem todas nas datas de início de DST
(outubro/novembro), não nas de fim de DST (fevereiro) — nenhuma das 5 datas de fevereiro
aparece nesta lista, em nenhum dos dois folds.

---

## 6. Contagem de registros por subsistema — data de virada e dia seguinte

| Data | Papel | N | NE | S | SE |
|---|---|---|---|---|---|
| 2015-02-21 | sábado (virada) | 24 | 24 | 24 | 24 |
| 2015-02-22 | domingo (virada) | 24 | 24 | 24 | 24 |
| 2015-02-23 | dia seguinte | 24 | 24 | 24 | 24 |
| 2016-02-20 | sábado (virada) | 24 | 24 | 24 | 24 |
| 2016-02-21 | domingo (virada) | 24 | 24 | 24 | 24 |
| 2016-02-22 | dia seguinte | 24 | 24 | 24 | 24 |
| 2017-02-18 | sábado (virada) | 24 | 24 | 24 | 24 |
| 2017-02-19 | domingo (virada) | 24 | 24 | 24 | 24 |
| 2017-02-20 | dia seguinte | 24 | 24 | 24 | 24 |
| 2018-02-17 | sábado (virada) | 24 | 24 | 24 | 24 |
| 2018-02-18 | domingo (virada) | 24 | 24 | 24 | 24 |
| 2018-02-19 | dia seguinte | 24 | 24 | 24 | 24 |
| 2019-02-16 | sábado (virada) | 24 | 24 | 24 | 24 |
| 2019-02-17 | domingo (virada) | 24 | 24 | 24 | 24 |
| 2019-02-18 | dia seguinte | 24 | 24 | 24 | 24 |

24 em todas as 15 linhas × 4 subsistemas = 60 combinações, sem exceção.

---

## 7. O que os dados explicam e o que não explicam

O que os dados explicam, com as tabelas acima:

- Por que a diferença reportada em `reports/01_dst_verificacao.md` seção 6.3 é 3,0 horas:
  o método usado ali (`ambiguous="raise"`) descarta inteiramente a única linha local
  correspondente à hora ambígua (sábado 23:00), e essa linha, se não fosse descartada,
  corresponderia a 2 instantes UTC diferentes (seção 2 e 3 acima) — 01:00 e 02:00 UTC do
  domingo — o que produz um intervalo de 3 horas entre o UTC anterior (00:00) e o
  posterior (03:00), com 2 posições vazias no meio.
- Os dados não mostram nenhuma linha classificada como INEXISTENTE nas janelas de
  fevereiro (isso só ocorre nas janelas de outubro/novembro).
- Os dados não sustentam a hipótese de que o valor da hora ambígua é a soma das duas
  horas físicas reais que ela representa: a razão observado/referência da hora ambígua,
  nas 5 viradas, varia entre 0,8977 e 1,0637 — nenhuma está perto de 2 (seção 4).
- Sob `fold=0` ou `fold=1` (métodos que não descartam a linha ambígua), a hora local
  ambígua de fevereiro gera um UTC que não colide com nenhum outro UTC da série — as
  únicas colisões de UTC nesses dois métodos ocorrem nas datas de outubro/novembro,
  não nas de fevereiro (seção 5).

O que os dados não explicam:

- Por que a linha correspondente à hora local ambígua de fevereiro contém um único
  valor numérico (não dois, não vazio, não uma soma) armazenado sob um único
  `din_instante`, em vez de ter duas linhas (uma por instante físico real) ou nenhuma.
  Os dados mostram QUE isso acontece (seção 1 e 2) mas não contêm informação sobre POR
  QUE o arquivo foi gerado dessa forma.

---

## 8. Reprodutibilidade

- Ambiente: Python 3.12.10, `zoneinfo` (tzdata embutido), dependências pinadas em
  [`requirements.txt`](../requirements.txt).
- Script: [`src/probe_fev_gap.py`](../src/probe_fev_gap.py).
- Saídas intermediárias: [`data/interim/fev_gap_janelas.json`](../data/interim/fev_gap_janelas.json),
  [`data/interim/fev_gap_horas_faltantes.json`](../data/interim/fev_gap_horas_faltantes.json),
  [`data/interim/fev_gap_hipotese_soma.json`](../data/interim/fev_gap_hipotese_soma.json),
  [`data/interim/fev_gap_metodos.json`](../data/interim/fev_gap_metodos.json),
  [`data/interim/fev_gap_contagem.json`](../data/interim/fev_gap_contagem.json).
- Nenhum arquivo em `data/raw/` foi alterado. Nenhuma aleatoriedade foi usada em nenhuma
  etapa desta verificação.
