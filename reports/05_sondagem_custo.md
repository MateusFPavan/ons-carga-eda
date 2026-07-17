# Sondagem da fonte de custo de despacho

Fase de sondagem do Projeto 3. Nenhuma modelagem, nenhuma decisão sobre como usar o
custo. Apenas fatos verificados sobre os três datasets candidatos. Gerado em
2026-07-17.

---

## 1. Localização, licença e schedule — os três datasets

| Dataset | URL do dataset | URL do dicionário |
|---|---|---|
| CMO Semi-Horário | https://dados.ons.org.br/dataset/cmo-semi-horario | https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/cmo_tm/DicionarioDados_Cmo_Semi_Horario.pdf |
| CMO Semanal | https://dados.ons.org.br/dataset/cmo-semanal | https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/cmo_se/DicionarioDados_Cmo_Semanal.pdf |
| CVU das Usinas Térmicas | https://dados.ons.org.br/dataset/cvu-usitermica | https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/cvu_usitermica_se/DicionarioDados_CVU_UsinaTermica.pdf |

Os três: organização ONS, licença **CC-BY** (mesma do dataset de carga já usado no
projeto).

| Dataset | Anos disponíveis (listados no portal) | Formatos | Schedule de atualização declarado |
|---|---|---|---|
| CMO Semi-Horário | 2020–2026 | CSV, XLSX, PARQUET | Diário, 12:00 e 19:00 (BRT) |
| CMO Semanal | 2005–2026 | CSV, XLSX, PARQUET | Diário, 12:00 e 19:00 (BRT) |
| CVU das Usinas Térmicas | 2005–2026 | CSV, XLSX, PARQUET | Diário, 12:00 e 19:00 (BRT) |

**Fato relevante para a Tarefa 4:** o CMO Semi-Horário — o único dos três com
granularidade sub-horária — **não cobre 2015**. A lista de recursos do dataset no
portal só tem arquivos de 2020 em diante. CMO Semanal e CVU cobrem 2005–2026, bem
além da janela do projeto (2015–2026).

A lista de anos acima vem da página do dataset (recursos listados), não de download
de cada ano — só a amostra de 2024 de cada um foi efetivamente baixada e inspecionada
(seção 3).

### Esquema declarado nos três dicionários

**CMO Semi-Horário** (resultado do modelo DESSEM; CMO por barra, agregado por
subsistema ponderado pela carga):

| Campo | Código | Tipo | Formato | Nulo | Zero | Negativo |
|---|---|---|---|---|---|---|
| Código do Subsistema | `id_subsistema` | TEXTO | 3 posições | Não | ---- | ---- |
| Nome do Subsistema | `nom_subsistema` | TEXTO | 20 posições | Não | ---- | ---- |
| Data de referência | `din_instante` | DATETIME | YYYY-MM-DD HH:MM:SS | Não | ---- | ---- |
| Valor do CMO em R$/MWh | `val_cmo` | FLOAT | — | Não | **Sim** | **Sim** |

**CMO Semanal** (resultado do modelo DECOMP; por semana operativa, subsistema e
patamar de carga):

| Campo | Código | Tipo | Formato | Nulo | Zero | Negativo |
|---|---|---|---|---|---|---|
| Código do Subsistema | `id_subsistema` | TEXTO | 3 posições | Não | ---- | ---- |
| Nome do Subsistema | `nom_subsistema` | TEXTO | 20 posições | Não | ---- | ---- |
| Data de referência da Semana Operativa | `din_instante` | DATETIME | YYYY-MM-DD HH:MM:SS | Não | ---- | ---- |
| CMO Médio Semanal, **em R$/MW** | `val_cmomediasemanal` | FLOAT | — | Não | Sim | Sim |
| CMO patamar leve, em R$/MWh | `val_cmoleve` | FLOAT | — | Não | Sim | Sim |
| CMO patamar médio, em R$/MWh | `val_cmomedia` | FLOAT | — | Não | Sim | Sim |
| CMO patamar pesado, em R$/MWh | `val_cmopesada` | FLOAT | — | Não | Sim | Sim |

**Divergência de unidade dentro do próprio dicionário, reportada como está escrita:**
o dicionário declara `val_cmomediasemanal` em **R$/MW**, enquanto as outras 3 colunas
de valor do mesmo dataset (`val_cmoleve`, `val_cmomedia`, `val_cmopesada`) são
declaradas em **R$/MWh**. Não investigado se é erro de digitação do dicionário ou
diferença real de unidade — reportado como está.

**CVU das Usinas Térmicas** (considerado no Programa Mensal da Operação — PMO,
conforme utilizado na execução do modelo **DECOMP** — o dicionário não cita NEWAVE
nem DESSEM no texto da descrição, apenas DECOMP):

| Campo | Código | Tipo | Formato | Nulo | Zero | Negativo |
|---|---|---|---|---|---|---|
| Data de Início da Semana Operativa | `dat_iniciosemana` | DATE | YYYY-MM-DD | Não | ---- | ---- |
| Data de Fim da Semana Operativa | `dat_fimsemana` | DATE | YYYY-MM-DD | Não | ---- | ---- |
| Ano de Referência do PMO | `ano_referencia` | INTEIRO | — | Não | Não | Não |
| Mês de Referência do PMO | `mes_referencia` | INTEIRO | — | Não | Não | Não |
| Número da Revisão PMO | `num_revisao` | INTEIRO | — | Não | Sim | Não |
| Nome do Estudo da Semana Operativa | `nom_semanaoperativa` | TEXTO | 150 posições | Não | ---- | ---- |
| Código da usina nos modelos de planejamento | `cod_usinaplanejamento` | INTEIRO | — | Não | Não | Não |
| Código do Subsistema | `id_subsistema` | TEXTO | 3 posições | Não | ---- | ---- |
| Nome do Subsistema | `nom_subsistema` | TEXTO | 20 posições | Não | ---- | ---- |
| Nome da Usina | `nom_usina` | TEXTO | 150 posições | Não | ---- | ---- |
| Valor do CVU, em R$/MWh | `val_cvu` | DECIMAL(18,2) | — | Não | Sim | **Não** |

Diferente dos dois CMOs, o dicionário do CVU declara explicitamente que **não permite
valor negativo**.

---

## 2. Amostras baixadas (2024, Parquet)

| Arquivo | URL | Tamanho | SHA-256 |
|---|---|---|---|
| `custo/cmo_semi_horario_2024.parquet` | `.../cmo_tm/CMO_SEMIHORARIO_2024.parquet` | 391.724 bytes | `05345ccb0e1f2730...` |
| `custo/cmo_semanal_2024.parquet` | `.../cmo_se/CMO_SEMANAL_2024.parquet` | 6.683 bytes | `4dde295936633d18...` |
| `custo/cvu_usina_termica_2024.parquet` | `.../cvu_usitermica_se/CVU_USINA_TERMICA_2024.parquet` | 26.001 bytes | `f8fd4eef40ea3b9c...` |

Registrados em `data/raw/MANIFEST.json` com URL completa, timestamp local/UTC, tamanho
e SHA-256 completo — mesmo esquema do resto do projeto.

---

## 3. As três amostras — esquema observado, granularidade, subsistema, unidade, estatística

### 3.1 CMO Semi-Horário 2024

**Colunas observadas:** `id_subsistema`, `nom_subsistema`, `din_instante`, `val_cmo` —
**idênticas** às 4 colunas declaradas no dicionário. Nenhuma divergência de esquema.

**Granularidade real:** diferença entre timestamps consecutivos é de 1.800 segundos
(30 minutos) na quase totalidade dos casos — **confirma "semi-horário" = 30 minutos**,
não horário. Um único valor de diferença distinto aparece além de 1.800s: 88.200
segundos (24h30min), no ponto onde há um dia inteiro ausente (ver abaixo).

**Recorte por subsistema:** `id_subsistema` ∈ {`N`, `NE`, `S`, `SE`} — os mesmos 4
subsistemas do dataset de carga. **O CMO é por subsistema, não nacional** (17.376
linhas por subsistema, distribuídas igualmente entre os 4).

**Cobertura e buracos, 2024:** primeiro instante `2024-01-01 00:00:00`, último
`2024-12-31 23:30:00`. Total de linhas: 69.504. Um ano de 366 dias (2024 é bissexto) em
grade de 30 min e 4 subsistemas produziria 366 × 48 × 4 = 70.272 linhas — **768 a
menos que o observado**. Checado por subsistema (SE): todo dia presente tem
exatamente 48 registros (nenhum dia parcial), mas **4 dias do calendário estão
inteiramente ausentes**: 2024-02-08, 2024-02-17, 2024-07-13, 2024-12-29 (368 × 48 × 4
não bate porque na verdade são 362 dias presentes, não 366; 362 × 48 × 4 = 69.504,
que bate exatamente com o total observado).

**Unidade:** R$/MWh, conforme dicionário.

**Estatística `val_cmo` (R$/MWh), 69.504 valores, 0 nulos:**

| Mín | Q1 | Mediana | Média | Q3 | Máx | N negativos | N zeros |
|---|---|---|---|---|---|---|---|
| -10,44 | 0,05 | 13,265 | 118,10 | 102,16 | 2.366,81 | 77 | 8.989 |

Valores negativos (77) e zeros (8.989) existem na amostra — consistente com o
dicionário, que permite ambos.

### 3.2 CMO Semanal 2024

**Colunas observadas:** `id_subsistema`, `nom_subsistema`, `din_instante`,
`val_cmomediasemanal`, `val_cmoleve`, `val_cmomedia`, `val_cmopesada` — idênticas às 7
colunas declaradas. Nenhuma divergência de esquema.

**Granularidade real:** diferença entre datas consecutivas é sempre 7 dias — confirma
semanal, sem exceção na amostra.

**Recorte por subsistema:** mesmos 4 (`N`, `NE`, `S`, `SE`).

**Cobertura:** primeira semana `2024-01-05`, última `2024-12-27`. 208 linhas = 52
semanas × 4 subsistemas — **bate exatamente**, sem buraco.

**Unidade:** conforme declarado no dicionário — `val_cmomediasemanal` em R$/MW,
as outras 3 em R$/MWh (ver divergência de unidade na seção 1).

**Estatísticas (R$/MWh ou R$/MW conforme coluna), 208 valores cada, 0 nulos:**

| Coluna | Mín | Q1 | Mediana | Média | Q3 | Máx | N negativos | N zeros |
|---|---|---|---|---|---|---|---|---|
| `val_cmomediasemanal` | 0,00 | 0,0375 | 16,83 | 99,66 | 95,68 | 624,81 | 0 | 42 |
| `val_cmoleve` | 0,00 | 0,0375 | 16,565 | 97,84 | 94,23 | 614,64 | 0 | 42 |
| `val_cmomedia` | 0,00 | 0,0375 | 16,92 | 100,39 | 96,31 | 628,31 | 0 | 42 |
| `val_cmopesada` | 0,00 | 0,04 | 17,285 | 102,55 | 98,72 | 640,93 | 0 | 42 |

**Fato:** nenhuma das 4 colunas tem valor negativo nesta amostra, embora o dicionário
permita (`Permite valor negativo: Sim`). Zeros existem nas 4 colunas (42 de 208 cada,
21%).

### 3.3 CVU das Usinas Térmicas 2024

**Colunas observadas:** as 11 colunas declaradas, nomes idênticos. Nenhuma divergência
de esquema.

**Granularidade real:** organizado por semana operativa (`dat_iniciosemana` /
`dat_fimsemana`) — 52 semanas distintas na amostra, de `2023-12-30` (início da semana
que contém 2024-01-01) a `2024-12-21`. Não é estritamente mensal: a granularidade de
linha é semana × usina × revisão, mas cada linha também carrega `mes_referencia` (o
mês do PMO — Programa Mensal da Operação — ao qual aquela semana pertence) e
`num_revisao` (0 a 4 na amostra — o PMO de um mês é revisado várias vezes ao longo do
mês). `nom_semanaoperativa` confirma o vínculo, com valores como `"PMO Janeiro 2024"`.

**Por usina individual:** sim — 114 nomes de usina distintos (`nom_usina`), 114
códigos distintos (`cod_usinaplanejamento`), correspondência 1:1 entre nome e código
na amostra.

**Recorte por subsistema:** mesmos 4 (`N`, `NE`, `S`, `SE`) — cada usina pertence a um
subsistema.

**Programa/modelo referenciado:** o dicionário cita **PMO** (Programa Mensal da
Operação) como o programa de referência e **DECOMP** como o modelo de execução, no
texto da descrição do dado. NEWAVE e DESSEM não aparecem no texto do dicionário desta
versão (24-09-2025) — só nas tags gerais do dataset no portal, que não fazem parte do
dicionário de dados formal.

**Unidade:** R$/MWh, conforme dicionário.

**Estatística `val_cvu` (R$/MWh), 4.881 valores, 0 nulos:**

| Mín | Q1 | Mediana | Média | Q3 | Máx | N negativos | N zeros |
|---|---|---|---|---|---|---|---|
| 0,00 | 108,24 | 330,64 | 507,80 | 930,65 | 3.681,59 | 0 | 854 |

Nenhum valor negativo (consistente com o dicionário, que declara não permitir).
854 zeros de 4.881 (17,5%).

---

## 4. CMO — pontos específicos da Tarefa 4

- **Granularidade nativa do Semi-Horário: 30 minutos**, confirmada empiricamente (seção
  3.1). A grade de carga do projeto é horária (1 registro/hora). Uma hora de carga
  corresponde a 2 registros de CMO semi-horário — nenhuma agregação entre os dois foi
  feita aqui.
- **Por subsistema, não nacional** — confirmado nos dois CMOs (4 valores distintos de
  `id_subsistema` em cada linha de tempo, não 1 valor nacional único).
- **Cobertura temporal:** CMO Semi-Horário **não vai até 2015** — o portal só lista
  recursos de 2020 a 2026 (seção 1). CMO Semanal vai até 2005, cobrindo toda a janela
  do projeto (2015–2026) e além.

---

## 5. CVU — pontos específicos da Tarefa 5

- **Por usina individual:** sim, confirmado (114 usinas na amostra de 2024).
- **Tem data de vigência:** sim — `dat_iniciosemana` e `dat_fimsemana` por linha,
  delimitando a semana operativa em que aquele valor de CVU vale.
- **É mensal?** Não estritamente — a granularidade de linha é semanal (por semana
  operativa), mas cada semana está associada a um mês de referência do PMO
  (`mes_referencia`) e pode ter múltiplas revisões dentro do mês (`num_revisao`, 0–4
  na amostra).
- **114 usinas** na amostra de 2024 (contagem exata, seção 3.3).
- **Programa/modelo:** PMO (programa) e DECOMP (modelo de execução), conforme texto do
  dicionário — ver seção 3.3.

---

## 6. Cobertura cruzada — CMO × carga do SE/CO, em base horária

| Fonte | Janela confirmada |
|---|---|
| Carga SE/CO (já no projeto) | 2015-01-01 00:00:00 a 2026-07-15 23:00:00 (ver `reports/FACTS.md`) |
| CMO Semi-Horário (subsistema SE) | Recursos listados no portal: 2020–2026. Conteúdo efetivamente baixado e verificado: só 2024 (seção 3.1). |
| CMO Semanal (subsistema SE) | Recursos listados no portal: 2005–2026. Conteúdo efetivamente baixado e verificado: só 2024 (seção 3.2). |

**Limite superior do que pode ser usado, baseado no que foi listado no portal (não
totalmente baixado nem verificado ano a ano):** a interseção entre carga (2015–2026) e
CMO Semi-Horário (2020–2026, por listagem) é **2020–2026** — 6 dos 12 anos de carga já
baixados no projeto não têm CMO semi-horário disponível, se a listagem do portal
estiver correta para todos os anos intermediários (2021, 2022, 2023 não foram
individualmente baixados nem verificados aqui, só 2024). CMO Semanal, por cobrir desde
2005, não restringe a janela 2015–2026 do projeto — mas é semanal, não horário.

**Reconciliação de granularidade não feita:** carga é horária, CMO Semi-Horário é de
30 minutos, CMO Semanal é semanal (com 3 patamares de carga, não 24 valores por dia).
Nenhuma agregação ou casamento de grade temporal entre carga e CMO foi feito nesta
sondagem.

---

## 7. A pergunta central — o dado liga MW a R$, ou só dá o preço?

**Fato observado, nos três dicionários e nas três amostras:** nenhum dos três datasets
contém uma coluna de quantidade de energia em MW ou MWh associada a um valor
monetário already-computed em R$. Os três contêm exclusivamente **preço por unidade de
energia**:

- CMO Semi-Horário: `val_cmo`, R$/MWh, por subsistema, por instante de 30 minutos.
- CMO Semanal: 4 colunas de preço (R$/MW ou R$/MWh conforme a coluna), por subsistema,
  por semana e patamar de carga.
- CVU: `val_cvu`, R$/MWh, por usina térmica, por semana operativa.

Nenhuma das três colunas de valor é uma "quantidade × preço" já calculada, e nenhuma
delas faz referência a um "erro de previsão" ou a uma diferença entre carga prevista e
carga realizada — esse conceito não existe em nenhum dos três dicionários nem apareceu
em nenhuma das três amostras.

**Para ligar um erro de carga em MW a um custo em R$**, os dados disponíveis exigiriam
uma multiplicação feita fora do dado bruto: um erro de X MW, numa hora e subsistema
específicos, avaliado ao preço (CMO ou CVU) daquela hora/subsistema — essa
multiplicação e a suposição de que o erro "vale" o CMO (em vez do CVU, ou de outro
preço) não estão no dado, seriam uma decisão de modelagem a ser tomada fora desta
sondagem.

---

## Reprodutibilidade

- Ambiente: Python 3.12.10, dependências pinadas em [`requirements.txt`](../requirements.txt).
- Scripts: [`src/download_custo.py`](../src/download_custo.py) (download + manifesto),
  [`src/probe_custo.py`](../src/probe_custo.py) (sondagem das 3 amostras).
- Saída intermediária: [`data/interim/probe_custo.json`](../data/interim/probe_custo.json).
- Arquivos brutos: `data/raw/custo/*.parquet` (3 arquivos, registrados em
  `data/raw/MANIFEST.json`).
- Nenhum arquivo pré-existente em `data/raw/` foi alterado. Nenhuma série completa foi
  baixada — só as 3 amostras de 2024. Nenhuma aleatoriedade foi usada.
