# Efeito do DST no formato da curva + viabilidade de temperatura sem vazamento

Dois testes independentes. Nenhuma limpeza, correção ou decisão foi feita. Gerado em
2026-07-16.

---

# PARTE A — Efeito do DST no perfil de consumo (SE/CO)

**Hipótese testada:** o horário de verão alterou o formato da curva de carga (não só
deslocou o relógio). Se verdadeiro, verões com DST devem ter pico noturno mais tarde
e/ou mais baixo (em relação ao pico da tarde) que verões sem DST, na mesma hora de
relógio.

## A0. Recorte usado

Meses de calendário inteiramente dentro da vigência de DST em todas as 4 temporadas
com DST (a temporada mais tardia começa 2018-11-04; a mais precoce termina
2016-02-21) são **dezembro e janeiro** — os únicos 2 meses de calendário 100% cobertos
pela vigência nas 4 temporadas. Os mesmos 2 meses são usados nas 4 temporadas sem DST,
para manter os grupos no mesmo recorte sazonal.

| Regime | Verões incluídos |
|---|---|
| COM DST | dez/2015+jan/2016, dez/2016+jan/2017, dez/2017+jan/2018, dez/2018+jan/2019 |
| SEM DST | dez/2021+jan/2022, dez/2022+jan/2023, dez/2023+jan/2024, dez/2024+jan/2025 |

2019-20 e 2020-21 excluídos por completo (transição do decreto + pandemia). Os 9
timestamps de virada já identificados em `reports/01_dst_verificacao.md` foram
excluídos do cálculo — nenhum deles cai em dezembro ou janeiro, então essa exclusão não
removeu nenhuma linha do recorte usado aqui.

## A4. Número de dias em cada grupo

| Regime | Tipo de dia | N dias | N registros | Registros esperados (n_dias×24) |
|---|---|---|---|---|
| com_dst | dia útil | 176 | 4.224 | 4.224 |
| com_dst | fim de semana | 72 | 1.728 | 1.728 |
| sem_dst | dia útil | 177 | 4.248 | 4.248 |
| sem_dst | fim de semana | 71 | 1.704 | 1.704 |

Registros observados = esperados em todos os 4 casos (nenhum buraco no recorte).

## A1. Perfil horário médio (24 pontos), bruto e normalizado por média diária (A3)

Normalização (A3): cada valor horário dividido pela média dos 24 valores do próprio dia,
antes de agregar — remove o nível (tendência de crescimento entre 2015 e 2025), mantém
só o formato relativo do dia.

### Dias úteis

| Hora | com_dst bruto (MW médios) | sem_dst bruto (MW médios) | com_dst normalizado | sem_dst normalizado |
|---|---|---|---|---|
| 00h | 36.724,38 | 40.975,20 | 0,9328 | 0,9287 |
| 01h | 34.681,91 | 39.092,02 | 0,8811 | 0,8860 |
| 02h | 33.442,72 | 37.860,61 | 0,8498 | 0,8581 |
| 03h | 32.745,29 | 37.171,21 | 0,8320 | 0,8426 |
| 04h | 32.628,37 | 37.126,89 | 0,8290 | 0,8416 |
| 05h | 33.365,44 | 37.415,15 | 0,8477 | 0,8479 |
| 06h | 34.388,95 | 38.836,30 | 0,8733 | 0,8793 |
| 07h | 36.260,19 | 41.499,50 | 0,9204 | 0,9388 |
| 08h | 39.171,75 | 43.910,99 | 0,9940 | 0,9925 |
| 09h | 41.202,26 | 45.194,15 | 1,0454 | 1,0211 |
| 10h | 42.490,65 | 46.137,94 | 1,0782 | 1,0421 |
| 11h | 42.617,79 | 46.422,43 | 1,0816 | 1,0483 |
| 12h | 42.407,72 | 46.196,10 | 1,0763 | 1,0433 |
| 13h | 43.475,38 | 47.121,41 | 1,1026 | 1,0641 |
| 14h | 44.124,73 | 47.899,14 | 1,1187 | 1,0819 |
| 15h | 44.137,24 | 48.250,80 | 1,1191 | 1,0906 |
| 16h | 43.597,47 | 48.169,83 | 1,1058 | 1,0899 |
| 17h | 41.774,11 | 46.749,51 | 1,0605 | 1,0594 |
| 18h | 39.589,00 | 46.860,63 | 1,0063 | 1,0636 |
| 19h | 39.525,92 | 49.188,08 | 1,0057 | 1,1173 |
| 20h | 42.260,01 | 49.162,63 | 1,0757 | 1,1164 |
| 21h | 42.546,60 | 48.336,85 | 1,0825 | 1,0968 |
| 22h | 41.963,88 | 46.452,57 | 1,0670 | 1,0534 |
| 23h | 39.915,47 | 43.967,72 | 1,0144 | 0,9966 |

### Fins de semana

| Hora | com_dst bruto (MW médios) | sem_dst bruto (MW médios) | com_dst normalizado | sem_dst normalizado |
|---|---|---|---|---|
| 00h | 35.904,65 | 40.481,69 | 1,0374 | 1,0257 |
| 01h | 33.985,65 | 38.682,68 | 0,9819 | 0,9804 |
| 02h | 32.662,75 | 37.343,26 | 0,9436 | 0,9466 |
| 03h | 31.788,41 | 36.499,64 | 0,9183 | 0,9251 |
| 04h | 31.353,45 | 36.065,15 | 0,9056 | 0,9140 |
| 05h | 31.255,04 | 35.270,66 | 0,9027 | 0,8934 |
| 06h | 30.610,11 | 34.982,77 | 0,8835 | 0,8848 |
| 07h | 30.628,79 | 35.767,14 | 0,8838 | 0,9035 |
| 08h | 32.114,90 | 36.807,58 | 0,9265 | 0,9288 |
| 09h | 33.526,88 | 37.661,76 | 0,9673 | 0,9500 |
| 10h | 34.499,09 | 38.388,13 | 0,9956 | 0,9684 |
| 11h | 34.948,24 | 38.938,21 | 1,0090 | 0,9827 |
| 12h | 35.015,70 | 39.030,26 | 1,0111 | 0,9853 |
| 13h | 34.947,46 | 38.874,51 | 1,0089 | 0,9815 |
| 14h | 34.898,62 | 38.893,63 | 1,0074 | 0,9825 |
| 15h | 34.977,73 | 39.306,79 | 1,0098 | 0,9940 |
| 16h | 35.143,59 | 40.198,21 | 1,0150 | 1,0180 |
| 17h | 35.533,41 | 41.419,67 | 1,0270 | 1,0506 |
| 18h | 35.815,88 | 43.204,01 | 1,0358 | 1,0974 |
| 19h | 36.800,55 | 45.767,78 | 1,0647 | 1,1639 |
| 20h | 39.731,93 | 45.569,38 | 1,1500 | 1,1590 |
| 21h | 39.484,58 | 44.435,68 | 1,1430 | 1,1297 |
| 22h | 38.352,66 | 42.929,20 | 1,1102 | 1,0908 |
| 23h | 36.706,15 | 41.106,22 | 1,0620 | 1,0439 |

Gráficos (sobreposição com_dst × sem_dst, bruto e normalizado, lado a lado):
[`figures/f1_dst_efeito_perfil_dia_util.png`](figures/f1_dst_efeito_perfil_dia_util.png),
[`figures/f2_dst_efeito_perfil_fim_de_semana.png`](figures/f2_dst_efeito_perfil_fim_de_semana.png).

## A2 / A3. Pico noturno, valor do pico e razão pico/vale, por regime

O perfil de dia útil é bimodal (um máximo local à tarde, ~12–17h, e um máximo local à
noite, ~18–23h). Por isso, além do pico global (o maior valor do dia, seja tarde ou
noite), a tabela reporta separadamente o pico dentro da janela da tarde e o pico dentro
da janela da noite.

### Bruto (MW médios)

| Regime | Tipo de dia | Hora pico global | Valor pico global | Hora pico tarde (12–17h) | Valor pico tarde | Hora pico noite (18–23h) | Valor pico noite | Hora vale | Valor vale | Razão pico/vale | Razão pico-noite/pico-tarde |
|---|---|---|---|---|---|---|---|---|---|---|---|
| com_dst | dia útil | 15h | 44.137,24 | 15h | 44.137,24 | 21h | 42.546,60 | 04h | 32.628,37 | 1,3527 | 0,9640 |
| sem_dst | dia útil | 19h | 49.188,08 | 15h | 48.250,80 | 19h | 49.188,08 | 04h | 37.126,89 | 1,3249 | 1,0194 |
| com_dst | fim de semana | 20h | 39.731,93 | 17h | 35.533,41 | 20h | 39.731,93 | 06h | 30.610,11 | 1,2980 | 1,1182 |
| sem_dst | fim de semana | 19h | 45.767,78 | 17h | 41.419,67 | 19h | 45.767,78 | 06h | 34.982,77 | 1,3083 | 1,1050 |

### Normalizado por média diária (A3)

| Regime | Tipo de dia | Hora pico global | Valor pico global | Hora pico tarde | Valor pico tarde | Hora pico noite | Valor pico noite | Hora vale | Valor vale | Razão pico/vale | Razão pico-noite/pico-tarde |
|---|---|---|---|---|---|---|---|---|---|---|---|
| com_dst | dia útil | 15h | 1,1191 | 15h | 1,1191 | 21h | 1,0825 | 04h | 0,8290 | 1,3498 | 0,9673 |
| sem_dst | dia útil | 19h | 1,1173 | 15h | 1,0906 | 19h | 1,1173 | 04h | 0,8416 | 1,3276 | 1,0245 |
| com_dst | fim de semana | 20h | 1,1500 | 17h | 1,0270 | 20h | 1,1500 | 06h | 0,8835 | 1,3016 | 1,1198 |
| sem_dst | fim de semana | 19h | 1,1639 | 17h | 1,0506 | 19h | 1,1639 | 06h | 0,8848 | 1,3154 | 1,1077 |

Fatos lidos diretamente da tabela, dia útil:
- Hora do pico noturno (janela 18–23h): com_dst = 21h; sem_dst = 19h — 2 horas de
  diferença no relógio.
- Razão pico-noite/pico-tarde: com_dst = 0,9640 (bruto) / 0,9673 (normalizado) — pico
  da noite MENOR que o da tarde; sem_dst = 1,0194 (bruto) / 1,0245 (normalizado) — pico
  da noite MAIOR que o da tarde.
- Hora e valor do vale (04h, ~0,83–0,84 da média diária) praticamente idênticos entre
  os dois regimes, bruto e normalizado.
- Razão pico/vale global: com_dst = 1,3527 (bruto) / 1,3498 (normalizado); sem_dst =
  1,3249 (bruto) / 1,3276 (normalizado) — diferença de 2 a 3 pontos percentuais.

Fatos lidos diretamente da tabela, fim de semana:
- Hora do pico noturno: com_dst = 20h; sem_dst = 19h — 1 hora de diferença.
- Razão pico-noite/pico-tarde maior que 1 nos dois regimes (sem inversão como no dia
  útil): com_dst = 1,1182 (bruto) / 1,1198 (normalizado); sem_dst = 1,1050 (bruto) /
  1,1077 (normalizado).

## A5. Limite a declarar

Os grupos comparados diferem em:
- ~7 anos de tendência de crescimento de carga (a média de dia útil bruta passa de
  ~38.900 MW médios em com_dst para ~44.600 MW médios em sem_dst, ~+15%).
- Mudança de matriz elétrica no período — geração solar distribuída cresceu de forma
  substancial entre as duas janelas comparadas, o que afeta a demanda líquida do
  sistema em horários de sol (isso não foi medido aqui, só citado como confundidor).
- Efeito pós-pandemia sobre padrões de trabalho remoto/híbrido, que também não foi
  medido aqui.

**Esta comparação NÃO isola o efeito do DST.** As diferenças de horário de pico e de
razão pico-noite/pico-tarde reportadas acima são consistentes com a hipótese, mas os
mesmos números são igualmente consistentes com qualquer combinação dos três
confundidores listados. A normalização por média diária (A3) remove o efeito de nível
(tendência de crescimento), não os efeitos de matriz elétrica ou de padrão de trabalho
pós-pandemia sobre o *formato* da curva.

---

# PARTE B — Viabilidade de temperatura sem vazamento

## B1. Endpoint e parâmetros

**Endpoint base:** `https://previous-runs-api.open-meteo.com/v1/forecast`

**Parâmetros usados em todas as chamadas:**
- `latitude`, `longitude` — coordenadas da cidade (tabela abaixo)
- `hourly` — `temperature_2m_previous_day1` (ou `temperature_2m_previous_day2` em B4)
- `start_date`, `end_date` — formato `YYYY-MM-DD`
- `timezone` — `America/Sao_Paulo`

Nenhum parâmetro `models` foi passado nas chamadas principais (B2–B4) — usa o modelo
default do endpoint para a variável. Testado explicitamente: passar `models=gfs_global`
ou `models=gfs_seamless` produziu resultado idêntico ao default (mesmos nulos, mesmo
primeiro timestamp não-nulo) na janela de março/2021 — não documentado como fato geral,
só verificado nesse recorte.

**Coordenadas usadas (centro urbano):**

| Cidade | Latitude | Longitude |
|---|---|---|
| São Paulo | -23,5505 | -46,6333 |
| Rio de Janeiro | -22,9068 | -43,1729 |
| Belo Horizonte | -19,9167 | -43,9345 |
| Brasília | -15,7797 | -47,9297 |
| Goiânia | -16,6869 | -49,2648 |

**Significado de `_previous_dayN`** (conforme documentação): `previous_day1` é o valor
previsto 24h antes do instante válido; `previous_day2`, 48h antes; e assim até
`previous_day7`.

**Cobertura declarada na documentação:** maioria dos modelos arquivada desde
janeiro/2024; GFS `temperature_2m` desde março/2021; JMA GSM/MSM desde 2018 (sem cidade
sul-americana citada explicitamente para esse último). Testado empiricamente em B2/B3
abaixo — não confiado sem teste.

## B2. Teste de 3 janelas × 5 cidades — `temperature_2m_previous_day1`

| Cidade | Janela | Status | Horas retornadas | Horas esperadas | Nulos | Timezone retornado | UTC offset (s) |
|---|---|---|---|---|---|---|---|
| São Paulo | 2021-03-01 a 2021-03-31 | ok | 744 | 744 | 549 | America/Sao_Paulo | -10800 |
| São Paulo | 2024-01-01 a 2024-01-31 | ok | 744 | 744 | 441 | America/Sao_Paulo | -10800 |
| São Paulo | 2026-01-01 a 2026-01-31 | ok | 744 | 744 | 0 | America/Sao_Paulo | -10800 |
| Rio de Janeiro | 2021-03-01 a 2021-03-31 | ok | 744 | 744 | 549 | America/Sao_Paulo | -10800 |
| Rio de Janeiro | 2024-01-01 a 2024-01-31 | ok | 744 | 744 | 441 | America/Sao_Paulo | -10800 |
| Rio de Janeiro | 2026-01-01 a 2026-01-31 | ok | 744 | 744 | 0 | America/Sao_Paulo | -10800 |
| Belo Horizonte | 2021-03-01 a 2021-03-31 | ok | 744 | 744 | 549 | America/Sao_Paulo | -10800 |
| Belo Horizonte | 2024-01-01 a 2024-01-31 | ok | 744 | 744 | 441 | America/Sao_Paulo | -10800 |
| Belo Horizonte | 2026-01-01 a 2026-01-31 | ok | 744 | 744 | 0 | America/Sao_Paulo | -10800 |
| Brasília | 2021-03-01 a 2021-03-31 | ok | 744 | 744 | 549 | America/Sao_Paulo | -10800 |
| Brasília | 2024-01-01 a 2024-01-31 | ok | 744 | 744 | 441 | America/Sao_Paulo | -10800 |
| Brasília | 2026-01-01 a 2026-01-31 | ok | 744 | 744 | 0 | America/Sao_Paulo | -10800 |
| Goiânia | 2021-03-01 a 2021-03-31 | ok | 744 | 744 | 549 | America/Sao_Paulo | -10800 |
| Goiânia | 2024-01-01 a 2024-01-31 | ok | 744 | 744 | 441 | America/Sao_Paulo | -10800 |
| Goiânia | 2026-01-01 a 2026-01-31 | ok | 744 | 744 | 0 | America/Sao_Paulo | -10800 |

HTTP 200 em todas as 15 chamadas. `n_horas_retornadas == n_horas_esperadas` (744 = 31
dias × 24h) em todas — a API sempre devolve a grade completa do intervalo pedido, com
`null` nas posições sem dado, não uma lista mais curta.

Timezone retornado: `"America/Sao_Paulo"` em todas as 15 chamadas, offset fixo
`utc_offset_seconds = -10800` (UTC−3) mesmo na janela de março/2021 — não há
alternância de offset por DST no valor retornado (consistente com o Brasil não ter DST
desde 2019; a janela de março/2021 já é posterior à extinção do DST, então esse teste
não cobre um período com DST ativo).

Padrão de nulos idêntico nas 5 cidades, dentro de cada janela — sugere que os nulos são
função da janela temporal (cobertura do arquivo), não da localização geográfica dentro
do Brasil.

### Padrão diário dos nulos (São Paulo, detalhado hora a hora)

| Janela | Primeiro dia com pelo menos 1 valor não-nulo | Dias totalmente nulos antes desse ponto | Dias sem nenhum nulo depois desse ponto |
|---|---|---|---|
| mar/2021 | 2021-03-24 (2021-03-23 tem 21/24 nulos, parcial) | 2021-03-01 a 2021-03-22 (22 dias, 100% nulos) | 2021-03-24 a 2021-03-31 |
| jan/2024 | 2024-01-20 (2024-01-19 tem 9/24 nulos, parcial) | 2024-01-01 a 2024-01-18 (18 dias, 100% nulos) | 2024-01-20 a 2024-01-31 |
| jan/2026 | 2026-01-01 (sem nenhum nulo em toda a janela) | nenhum | toda a janela |

Em ambas as janelas de teste com nulos, a transição de "100% nulo" para "0% nulo" é
abrupta e ocorre num único dia de calendário — não há um período gradual de nulos
esparsos.

## B3. Bisecção — data mais antiga com dado (São Paulo, `temperature_2m_previous_day1`)

Limite inferior testado: 2015-01-01 (sem dado). Limite superior testado: 2021-06-01
(com dado).

| Data testada | Tem dado? |
|---|---|
| 2018-03-17 | não |
| 2019-10-24 | não |
| 2020-08-12 | não |
| 2021-01-05 | não |
| 2021-03-19 | não |
| 2021-04-25 | sim |
| 2021-04-06 | sim |
| 2021-03-28 | sim |
| 2021-03-23 | sim |
| 2021-03-21 | não |
| 2021-03-22 | não |

**Resultado: sem dado até 2021-03-22 (inclusive); com dado a partir de 2021-03-23**
(consistente com o detalhamento por dia de B2 acima, e com a data declarada na
documentação — "GFS 2m temperature desde março/2021" — no nível de mês, mas a
documentação não especifica o dia exato dentro de março).

## B4. Disponibilidade de `temperature_2m_previous_day2` (48h)

| Janela | Status | Horas retornadas | Nulos |
|---|---|---|---|
| 2021-03-01 a 2021-03-31 | ok | 744 | 573 |
| 2024-01-01 a 2024-01-31 | ok | 744 | 465 |
| 2026-01-01 a 2026-01-31 | ok | 744 | 0 |

`previous_day2` existe e responde (HTTP 200) nas mesmas 3 janelas. Tem mais nulos que
`previous_day1` na mesma janela em 2 dos 3 casos (573 vs. 549 em mar/2021; 465 vs. 441
em jan/2024) — corte de cobertura um pouco mais tardio para o lead time de 48h que para
o de 24h. Em jan/2026, 0 nulos nos dois.

## B5. Qualidade da própria previsão — comparação contra observado do INMET

**Não foi possível completar esta tarefa.** O endpoint que o próprio site do INMET usa
para servir dados horários de estação (`https://apitempo.inmet.gov.br/estacao/front/`,
identificado inspecionando o bundle JavaScript de `https://tempo.inmet.gov.br`,
arquivo `main.15ddd492.chunk.js`) exige um parâmetro `gcap` — um token gerado
client-side via `window.grecaptcha.execute(...)` (Google reCAPTCHA v3, `action:
"create_comment"`). Chamadas sem esse token retornam HTTP 204 (corpo vazio) — testado
em 3 padrões de rota (`/estacao/{d1}/{d2}/{cod}`, `/estacao/{cod}/{d1}/{d2}`, com e sem
barra final), 3 códigos de estação (A701 — São Paulo/Mirante, A001, A652), com e sem
sessão persistente de cookies, sempre 204.

Contornar ou resolver um CAPTCHA está fora do que posso fazer. Duas alternativas foram
verificadas e também não permitem completar B5 sem uma ação que também está fora do
escopo desta sondagem:
- **Portal BDMEP** (`https://bdmep.inmet.gov.br`) responde HTTP 200, mas é uma aplicação
  de página única cujo acesso aos dados históricos exige cadastro de usuário — criação
  de conta não é algo que eu deva fazer de forma não-interativa.
- **Download em lote anual** (`https://portal.inmet.gov.br/uploads/dadoshistoricos/2024.zip`)
  responde HTTP 200 sem CAPTCHA, mas é um arquivo de ~102 MB com todas as estações do
  Brasil para o ano inteiro — baixá-lo violaria a restrição de volume pequeno /
  não baixar anos inteiros desta sondagem.

**Estação identificada para referência futura, caso o cadastro no BDMEP seja feito
manualmente:** `SAO PAULO - MIRANTE`, código INMET `A701`, latitude -23,4962888,
longitude -46,6200666, operante desde 2006-07-24, situação "Operante" no momento da
consulta.

Como consequência, MAE, viés e erro no percentil 95 entre a previsão `previous_day1` e
a temperatura observada do INMET **não foram calculados** — não há dado observado para
comparar.

## B6. Registro em MANIFEST.json

18 arquivos de teste (15 de B2 + 3 de B4) foram baixados de fato para
`data/raw/temperatura/` e registrados em `data/raw/MANIFEST.json`, com o mesmo esquema
usado para os arquivos do ONS (URL, timestamp local e UTC, tamanho em bytes, SHA-256).
Nenhum arquivo do INMET foi baixado (B5 não produziu arquivo — ver acima). Nenhum
arquivo pré-existente do ONS em `data/raw/` foi alterado.

---

## Reprodutibilidade

- Ambiente: Python 3.12.10, dependências pinadas em [`requirements.txt`](../requirements.txt).
- Scripts: [`src/probe_dst_efeito.py`](../src/probe_dst_efeito.py) (Parte A),
  [`src/probe_temperatura.py`](../src/probe_temperatura.py) (Parte B, testes),
  [`src/download_temperatura_testes.py`](../src/download_temperatura_testes.py) (Parte B, download + manifesto).
- Saídas intermediárias: [`data/interim/dst_efeito.json`](../data/interim/dst_efeito.json),
  [`data/interim/temperatura_b2_janelas.json`](../data/interim/temperatura_b2_janelas.json),
  [`data/interim/temperatura_b3_bissecao.json`](../data/interim/temperatura_b3_bissecao.json),
  [`data/interim/temperatura_b4_previous_day2.json`](../data/interim/temperatura_b4_previous_day2.json),
  [`data/interim/temperatura_b2_padrao_diario_mar2021_sp.json`](../data/interim/temperatura_b2_padrao_diario_mar2021_sp.json),
  [`data/interim/temperatura_b2_padrao_diario_jan2024_sp.json`](../data/interim/temperatura_b2_padrao_diario_jan2024_sp.json).
- Arquivos brutos de temperatura: `data/raw/temperatura/*.json` (18 arquivos, registrados
  em `data/raw/MANIFEST.json`).
- Nenhum arquivo em `data/raw/` do ONS foi alterado. Nenhuma aleatoriedade foi usada em
  nenhuma etapa desta sondagem.
