# Escopo do Projeto 3 — Previsão de Carga SE/CO e Custo do Erro

> **Nota de status (adicionada 2026-08-17, seções 9/10/13 atualizadas
> 2026-08-19):** este era o documento de **planejamento pré-modelagem** do
> projeto — escrito antes de qualquer modelo ser rodado. O projeto **foi
> concluído** desde então, e as seções 9, 10 e 13 já foram reescritas para
> refletir o estado final (modelos comparados, estacionariedade testada, método
> de incerteza decidido), com os números conferidos contra `reports/FACTS.md`.
> **TimesFM 2.5 não foi avaliado** — permaneceu no plano original (§9) mas não há,
> em nenhum lugar deste repositório (código, `FACTS.md`, commits), evidência de
> que tenha sido de fato rodado; saiu do escopo silenciosamente, não foi "avaliado
> e descartado" (ver §9 para o detalhe). **Para os números finais, `reports/FACTS.md`
> (canônico) e `docs/technical_report.md` continuam a fonte primária** — o resto
> deste documento (decisões de escopo ainda válidas: seções 1-8, 11-12, 14-17)
> permanece registro da decisão original, não recalculado aqui.

Nenhum número neste documento foi calculado aqui. Todo valor citado vem de
[`reports/FACTS.md`](FACTS.md), a folha de fatos gerada por código a partir do dado
bruto (ou, para números de avaliação de modelo — seções 9, 10, 12f, 13 — de
`docs/technical_report.md` e dos scripts de modelo, conferidos contra `FACTS.md`
onde aplicável). As seções 9, 10 e 13 já foram atualizadas para o estado final;
onde alguma outra seção ainda descrever trabalho não feito ou exploração possível
(seção 16, "Extensões possíveis"), isso está marcado explicitamente como plano,
não como fato medido.

---

## 1. Pergunta de negócio

Prever a carga horária do subsistema SE/CO com horizonte day-ahead (24h à frente) e
traduzir o erro dessa previsão em custo, usando o preço marginal de operação do
próprio SIN como referência — em vez de um custo inventado ou de um proxy genérico.

---

## 2. Alvo e horizonte

- **Alvo:** subsistema SE/CO (`id_subsistema = "SE"`), carga horária. Os demais 3
  subsistemas (`N`, `NE`, `S`) ficam como checagem de robustez, não como alvo
  principal.
- **Horizonte:** day-ahead, 24 horas.
- **Justificativa:** day-ahead é o horizonte em que o despacho é decidido — é o
  horizonte em que um erro de previsão de carga se traduz em decisão de despacho
  errada, e portanto em custo.

---

## 3. Dados e proveniência

- Fonte: ONS — Curva de Carga Horária. URL base:
  `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/curva-carga-ho`.
- Licença: CC-BY, declarada pelo portal de dados abertos do ONS.
- 12 arquivos, um por ano, cobrindo 2015–2026.
- Snapshot baixado entre `2026-07-16T20:06:20.964290-03:00` e
  `2026-07-16T20:06:42.927332-03:00`, identificado por hash — SHA-256 do
  `MANIFEST.json` neste momento: `b8768ccee4f52c5c751db3ec80a86952da2cd97b2d5845174cd7cd1c87512bc4`
  (46 entradas no manifesto, incluindo os arquivos de custo e temperatura sondados
  depois).
- **Revisão retroativa:** os 10 arquivos de 2015–2024 compartilham a mesma data de
  `Last-Modified` do servidor (09 Oct 2025), numa sequência de poucos minutos —
  consistente com republicação em lote, não com 10 eventos independentes. O ONS
  declara um "processo de consistência recorrente" que revisa dados retroativamente.
  Por isso o snapshot é identificado por hash, não tratado como imutável — qualquer
  reprodução futura deste projeto pode encontrar valores diferentes nos mesmos anos.

---

## 4. Eixo temporal

**Decisão:** hora local (`America/Sao_Paulo`), sem conversão para UTC.

**Por quê:** converter para UTC introduz timestamps ambíguos e inexistentes sem
nenhum ganho demonstrado. Dos 9 timestamps especiais de virada de horário de verão
(2015–2019), 5 são ambíguos — cada um descrito como "1 hora física real não
registrada". Isso significa que manter o eixo em UTC não resolveria o problema:
criaria 5 horas físicas ausentes na série, em vez de resolvê-las.

**Consequência declarada:** o eixo temporal do projeto é regular no relógio (24
registros por dia, quase sempre), não contínuo no tempo físico. Isso é uma
característica do dado, registrada, não corrigida.

---

## 5. Janela

**Decisão:** 2015–2026, todo o histórico disponível no portal do ONS no momento do
snapshot — não cortada em 2020.

**Por quê não cortar em 2020:** o único fator que impõe um limite de 2020 é a
cobertura do CMO Semi-Horário (fonte de preço para a métrica de custo), que não
cobre 2015–2019. Isso não é motivo para limitar o modelo principal de previsão de
carga, que pode e deve usar todo o histórico disponível — a limitação de cobertura do
CMO afeta só a camada de tradução para custo, aplicada apenas ao período de teste.

---

## 6. Três quebras estruturais

1. **Fim do horário de verão (2019) — comportamental.** O Brasil observou DST até
   2019. O efeito no perfil de carga do SE/CO foi medido (dezembro+janeiro, 4 verões
   com DST vs. 4 sem DST, dias úteis e fins de semana separados):

   | Regime | Tipo de dia | Base | Hora pico tarde | Hora pico noite | Razão noite/tarde |
   |---|---|---|---|---|---|
   | com_dst | dia útil | bruto | 15h | 21h | 0,9640 |
   | sem_dst | dia útil | bruto | 15h | 19h | 1,0194 |
   | com_dst | fim de semana | bruto | 17h | 20h | 1,1182 |
   | sem_dst | fim de semana | bruto | 17h | 19h | 1,1050 |

   Contagem de dias na amostra: com_dst = 176 dias úteis + 72 fins de semana;
   sem_dst = 177 dias úteis + 71 fins de semana.

   **Limite declarado (não isolamento):** esta comparação NÃO isola o efeito do DST.
   Os grupos diferem em ~7 anos de tendência de crescimento de carga, mudança de
   matriz elétrica (geração solar distribuída cresceu no período) e efeitos
   pós-pandemia sobre padrões de trabalho — nenhum desses confundidores foi
   controlado.

2. **Pandemia (2020) — comportamental.** Mudança de padrão de consumo associada ao
   início da pandemia, um dos confundidores explicitamente não controlados na
   comparação do item 1 acima. Nenhuma métrica numérica isolada do efeito da pandemia
   está registrada em `FACTS.md`.

3. **Grade temporal do CMO Semi-Horário (2020+) — artificial, não física.** A
   cobertura do CMO Semi-Horário no portal do ONS começa em 2020, não em 2015 — é um
   limite de disponibilidade de dado, não um evento do sistema elétrico. É essa
   quebra, não uma quebra de comportamento de carga, que define o início do período
   de teste da métrica de custo (seção 12e).

---

## 7. Os 9 timestamps especiais e seu tratamento

Gerados por código (varredura via `zoneinfo("America/Sao_Paulo")` e `datetime.fold`,
2015-01-01 a 2019-12-31, nenhuma data hardcoded): 4 timestamps locais inexistentes
(início de DST) + 5 ambíguos (fim de DST) = 9 no total.

| Timestamp | Tipo |
|---|---|
| 2015-02-21 23:00:00 | ambíguo |
| 2015-10-18 00:00:00 | inexistente |
| 2016-02-20 23:00:00 | ambíguo |
| 2016-10-16 00:00:00 | inexistente |
| 2017-02-18 23:00:00 | ambíguo |
| 2017-10-15 00:00:00 | inexistente |
| 2018-02-17 23:00:00 | ambíguo |
| 2018-11-04 00:00:00 | inexistente |
| 2019-02-16 23:00:00 | ambíguo |

Nos 4 inexistentes, o valor vem vazio nos 4 subsistemas em 3 dos 4 casos; no quarto
(2018-11-04), 3 subsistemas vazios e o subsistema S com a string `0E-8` (única
notação científica em toda a coluna nos anos 2015–2024).

**Tratamento:** flag `is_dst_transition` nesses 9 timestamps, excluídos como origem
de previsão (não usados como ponto de partida para gerar uma previsão). Os vazios de
outubro NÃO são imputados — o dado ausente permanece ausente.

---

## 8. Divergências e omissões do dicionário oficial

Quatro casos, verificados na sondagem:

1. **Tipo declarado vs. observado.** `val_cargaenergiahomwmed` é declarado `FLOAT`
   no dicionário, mas está armazenado como texto (`str`) nos arquivos de 2015 a 2024
   — só vira `float64` em 2025 e 2026.
2. **Nulo declarado vs. observado.** A mesma coluna é declarada com "Permite valor
   nulo: Não", mas há 87 strings vazias no dataset inteiro.
3. **Unidade inconsistente dentro do mesmo dicionário.** O dicionário do CMO Semanal
   declara `val_cmomediasemanal` em R$/MW, enquanto as outras 3 colunas de valor do
   mesmo dataset (`val_cmoleve`, `val_cmomedia`, `val_cmopesada`) são declaradas em
   R$/MWh — mesma tabela, mesmo tipo de grandeza, unidades diferentes.
4. **Ausência de declaração de fuso horário.** Nem o dicionário do CMO Semi-Horário
   nem o da Curva de Carga Horária mencionam fuso, UTC ou hora local em nenhum lugar
   do texto — os dois usam a mesma frase idêntica para descrever a coluna de tempo,
   sem diferenciação. Nenhuma página de documentação geral do portal do ONS declara
   essa convenção (ver seção 12d).

---

## 9. Modelos, em ordem de prova

**Atualizado — estado final, ver nota de status no topo do documento.** Ordem de
prova efetivamente executada, cada modelo avaliado sob a mesma divisão temporal
(seção 11) e conferido contra `reports/FACTS.md`:

1. Sazonal-naive (régua, lag=168h) — MASE(sazonal) 1,2732.
2. SARIMA (1,1,1)(1,0,1,24) — MASE(sazonal) 1,3412 (pior que a régua por MASE, mas
   mais barato por custo — seção 12c). Prophet — MASE(sazonal) 1,1669.
3. Chronos-2 (120M, zero-shot, contexto 2048h) — MASE(sazonal) 0,4363, o vencedor
   decisivo. Números completos, custo e calibração: `reports/FACTS.md`,
   `docs/technical_report.md`.

**TimesFM 2.5 — não avaliado, achado registrado nesta atualização:** a versão
anterior deste documento listava TimesFM 2.5 junto com Chronos-2 como foundation
models planejados. Não há, em nenhum lugar do repositório (código, `FACTS.md`,
histórico de commits), evidência de que TimesFM 2.5 tenha sido de fato rodado —
nenhum script, nenhum resultado salvo, nenhuma menção fora deste arquivo. A
caracterização correta é: TimesFM 2.5 **saiu do escopo silenciosamente**, não foi
"avaliado e descartado" (o que implicaria uma rodada com resultado rejeitado). Só
Chronos-2 foi de fato avaliado entre os foundation models. Se TimesFM 2.5 foi
testado fora deste repositório, isso não está registrado aqui e não pode ser
citado como fato do projeto.

**Referência externa:** Simeone (2026, arXiv:2602.10848) avaliou quatro foundation
models (Chronos-Bolt, Chronos-2, Moirai-2, TinyTimeMixer) contra Prophet, SARIMA e
Seasonal Naive em dados horários de carga do ERCOT (Texas, 2020-2024), em hardware de
consumidor. Reportou MASE ~0,31 em contexto longo (2048h, day-ahead), redução de ~47%
sobre o Seasonal Naive, e calibração variável entre modelos (Chronos-2 bem calibrado;
Moirai-2 e Prophet superconfiantes).

**Resultado medido no SE/CO:** MASE(sazonal) do Chronos-2 aqui é 0,4363 — pior
(maior) que o ~0,31 de Simeone no ERCOT. **Isto NÃO é reprodução do resultado de
Simeone** — dado diferente (SE/CO vs. ERCOT), país diferente, quebras estruturais
diferentes (`src/modelo_chronos2.py`, impresso no stdout de cada rodada). A
CONCLUSÃO QUALITATIVA converge (foundation model zero-shot bate as baselines
clássicas por margem grande nos dois países); o NÚMERO não converge, e não era
esperado convergir. Contexto de 2048h foi de fato a configuração vencedora entre as
testadas (96 a 2048h, monótono), seguindo o protocolo de Simeone como ponto de
partida, não como alvo a bater.

---

## 10. Estacionariedade e sazonalidade

**Atualizado — estado final, ver nota de status no topo do documento.** Testada
formalmente antes de ajustar o SARIMA, não presumida da inspeção visual. Fonte:
docstring de `src/modelo_sarima.py` (decisão de método do modelo, não fato de dado
bruto — por isso não está em `reports/FACTS.md`, que cobre só dado bruto).

ADF e KPSS rodados em 4 janelas representativas de 60 dias, espalhadas por
2023-2026. **Ao nível bruto:** ADF sempre rejeita raiz unitária (p≈0) mas KPSS
rejeita estacionariedade em 3 das 4 janelas (p=0,01) — o conflito clássico
ADF-estacionário/KPSS-não-estacionário. **Após 1 diferença regular (d=1):** ADF e
KPSS concordam em estacionariedade nas 4 janelas. Diferenciação sazonal adicional
(D=1) foi testada e não mudou essa conclusão nem foi necessária além de d=1.

**Decisão tomada:** d=1, D=0 — a sazonalidade diária é capturada pelos termos
AR/MA sazonais em s=24, não por diferenciação sazonal. Ordem final do SARIMA:
(1,1,1)(1,0,1,24) — escolhida com esta evidência, não por busca em grade
exaustiva (SARIMA é baseline, não otimizado exaustivamente, por restrição
explícita da tarefa).

---

## 11. Validação

Walk-forward: a previsão será testada avançando no tempo, nunca com dado do futuro
disponível para o modelo em nenhum ponto do treino. O conjunto de teste final é
tocado uma única vez, ao final, para reportar o número de avaliação do projeto — não
usado para ajustar hiperparâmetro nem para escolher entre modelos candidatos.

**Período de avaliação:** inicia em 2024-01-01 e vai até o fim da série (2026).
Walk-forward day-ahead com origem deslizante: cada previsão usa todo o histórico
disponível ANTERIOR à sua origem (inclusive meses de 2024-2026 já decorridos), nunca
dados posteriores. O período de avaliação é tocado uma única vez.

Justificativa do início em 2024:

- coincide com a disponibilidade de temperatura sem vazamento (2024-01-20) e está
  dentro do período de CMO (2020+), permitindo avaliar erro estatístico, custo e a
  camada de temperatura sobre o mesmo período.
- deixa toda a pandemia e ambos os regimes de DST no passado das origens de
  previsão, disponíveis como contexto de treino.
- garante contexto contíguo >= 2048h antes de cada origem (histórico desde 2015),
  configuração de referência dos foundation models.
- ~2,5 anos de avaliação, centenas de origens day-ahead.
- consistente com o protocolo de STLF e de Simeone (2026): avaliação em janela
  recente com walk-forward day-ahead.

**Nota:** isto NÃO reduz o treino a <=2023. O modelo de carga usa todo o histórico
disponível em cada origem, como já declarado nas seções 5 e 12e.

---

## 12. Métrica

### 12a. É modelo declarado, não medição

Nenhum dos três datasets de custo sondados (CMO Semi-Horário, CMO Semanal, CVU)
contém uma ligação entre erro de carga (MW) e custo (R$) já calculada, nem o
conceito de "erro de previsão". Os três contêm preço. A métrica de negócio do
projeto é, portanto, um modelo declarado, não um dado observado:

> custo = |erro_MW| × CMO_horário × 1h

sob a suposição de que o erro de previsão é valorado ao custo marginal de operação
do subsistema naquela hora. Isto não é custo de despacho realizado — é uma
estimativa sob suposição explícita.

### 12b. Agregação do CMO: decisão testada

**Decisão:** agregar o CMO Semi-Horário (30 minutos) para a grade horária pela
**média** das duas semi-horas.

**Testada contra duas alternativas** (máximo das duas semi-horas; primeira
semi-hora), usando o sazonal-naive como instrumento de medição de erro, SE/CO, 2024:

| Variante | Custo total como % da média |
|---|---|
| (a) Média das 2 semi-horas | 100,0000% |
| (b) Máximo das 2 semi-horas | 102,7474% |
| (c) Primeira semi-hora | 99,3989% |

No agregado do ano, as três variantes ficam entre 99,3989% e 102,7474% da média —
próximas. Mas a escolha afeta **586 horas específicas** (de 8.688 na métrica de
custo) em mais de 10% cada — o mesmo conjunto de 586 horas nas duas comparações
(máximo vs. média, e primeira vs. média).

A média também evita CMO horário negativo: existem 77 valores semi-horários
negativos no ano (todos no subsistema NE — nenhum no SE), mas **0 horas** com a
média horária do CMO do SE saindo negativa.

### 12c. O custo é concentrado — MAPE médio não garante custo baixo

O limiar do decil 90 do CMO médio horário (SE, 2024) é 359,8710 R$/MWh. As 869 horas
acima desse limiar concentram **47,2269%** do custo total do ano (variante média).
Menos de 10% das horas respondem por quase metade do custo anual.

**Atualização (`FACTS.md`, número canônico atual):** o 47,2269% acima é
**só de 2024** — não é o número usado no relatório final. Sobre o período de
avaliação completo (2024-01-01 a 2026-07-15), a concentração é **25,2248%**
do custo nas 10% horas de CMO mais alto. Os dois números medem escopos
diferentes (um ano vs. o período de teste inteiro); citar um sem o outro
gerou confusão numa leitura anterior deste documento — por isso ambos ficam
registrados aqui, com a fonte de cada um.

**Consequência para a validação:** um modelo pode ter um MAPE médio baixo no ano
inteiro e ainda assim ter custo alto, se seus piores erros caírem justamente nas
horas de CMO mais alto. A avaliação de cada modelo (seção 11) vai reportar o erro
estratificado por faixa de CMO, não só o erro médio agregado — isso ainda não foi
feito para nenhum modelo além do sazonal-naive usado como instrumento nas sondagens.

### 12d. Fuso do CMO: fato derivado

Nenhum dos dois dicionários (CMO Semi-Horário, Curva de Carga) declara fuso
horário. Nenhuma documentação geral do portal do ONS declara essa convenção.

Três fatos brutos, medidos:

- Perfil intradiário do CMO (SE, 2024): pico às 18h (171,0205 R$/MWh), vale às 10h
  (81,8598 R$/MWh).
- Correlação entre o perfil horário do CMO e o perfil horário da carga SE/CO, sem
  deslocamento: 0,4501.
- Correlação sob a hipótese "CMO está em UTC, corrigir +3h": -0,0051 — a correção
  destrói a correlação em vez de melhorá-la.

**Fato derivado:** o CMO Semi-Horário é tratado como hora local (`America/Sao_Paulo`),
mesma convenção da carga — com base na convergência desses três fatos, não em
declaração de fonte.

**Divergência registrada, não resolvida por omissão:** `reports/07_fuso_cmo.md`,
aplicando um critério documental estrito (fuso só conta como determinado se
declarado pela fonte ou se o teste de deslocamento produzir um pico nítido e
isolado em ±3h), concluiu que **o fuso permanece desconhecido**. Este documento
regista uma leitura diferente do mesmo conjunto de fatos — tratar os três fatos
brutos acima como convergentes o suficiente para uma convenção de trabalho — sem
apagar essa conclusão. Confiança: alta por evidência, zero por documentação. Risco
explícito: se o ONS documentar o contrário, a métrica de custo precisa ser
recalculada.

### 12e. Cobertura: custo só no período de teste

O CMO Semi-Horário cobre 2020–2026 segundo a listagem do portal. Verificado ano a
ano (FACTS.md seção J7) para os anos que a avaliação de fato usa — **2024, 2025 e
2026: todos presentes, 0 valores nulos, faixa de valores plausível**, com poucos
dias individuais sem registro (4 em 2024, 1 em 2025, 2 em 2026 — já excluídos da
métrica de custo pelo próprio `calcular_custo`, não descartados em silêncio). 2020,
2021, 2022 e 2023 nunca foram baixados — não por lacuna, mas porque o período de
avaliação (2024-01-01+) nunca precisou deles. A métrica de custo é aplicada apenas
ao período de teste, nunca ao treino do modelo principal, que usa todo o histórico
2015–2026 de carga.

### 12f. Custo assimétrico: subprevisão penalizada mais que superprevisão

O custo simétrico (12a) trata erro-para-cima e erro-para-baixo como equivalentes —
mas operacionalmente não são. Subprever carga (previsto < real) significa faltar
energia: exige reserva rápida (peaker), compra emergencial ou, no extremo, corte de
carga. Superprever (previsto > real) só desperdiça capacidade já comprometida —
mais barato. Esta assimetria é consenso na literatura de previsão de carga.

**Definição, recomputada das previsões já salvas (não re-treina nada):**
- Superprevisão: custo = |erro| × CMO_horário × 1h (igual ao custo simétrico).
- Subprevisão: custo = |erro| × CMO_horário × fator_sub × 1h, `fator_sub` ≥ 1.

`fator_sub` não é cravado — é uma varredura de sensibilidade (1,0 controle
simétrico; 1,5, 2,0, 3,0 como faixa ancorada no custo relativo de reserva rápida
vs. base). O extremo real de escassez (VOLL — *Value of Lost Load*, ~US$10.000/MWh
em mercados como o MISO, ordens de magnitude acima do CMO típico) **não entra no
cálculo base**: aplica-se só nas horas de corte de carga efetivo, que este dataset
não identifica — declarado como limitação (seção 16), não modelado.

Resultados (custo por modelo × fator, viés direcional por modelo, robustez do
ranking): `reports/FACTS.md` seção L, `reports/tabela_custo_assimetrico.csv`,
`reports/tabela_vies_direcional.csv`, `reports/figures/resultado_8_custo_assimetrico.png`.

---

## 13. Incerteza

**Atualizado — estado final, ver nota de status no topo do documento.** Método
decidido: **quantis**, nativos de cada modelo onde disponível — conformal
prediction foi considerado nesta seção original, mas não foi necessário nem
usado, já que os quantis nativos/paramétricos bastaram. Bandas reportadas:
P10-P90 (80% nominal) e P05-P95 (90% nominal), exceto o naive semanal, que é uma
regra pontual sem incerteza (nenhum intervalo).

- **Chronos-2:** quantis nativos do modelo (`predict_quantiles`, níveis
  [0,05, 0,1, 0,5, 0,9, 0,95] — `docs/MODEL_CARD.md` seção 7).
- **SARIMA:** ponto e banda de `get_forecast()` — determinístico desde sempre,
  nenhuma correção necessária.
- **Prophet:** ponto de `predict()` (determinístico) + banda de
  `predictive_samples()`. **Correção de reprodutibilidade registrada:** a mediana
  precisou vir de `predict()`, não da mediana amostral de `predictive_samples()`
  — esta última introduzia ruído de reamostragem não controlado pela seed,
  confundível com vazamento de dado num teste de vazamento ingênuo. Diagnosticado
  e corrigido; ver docstring de `src/modelo_prophet.py`. Não se aplica a SARIMA
  nem a Chronos-2.

**Calibração medida** (`reports/tabela_comparativa.csv`, cobertura empírica vs.
nominal): Chronos-2 é o mais próximo do nominal nos dois níveis (79,35% @80%,
88,93% @90%); SARIMA super-cobre (84,48% @80%, 92,52% @90% — banda larga demais);
Prophet sub-cobre levemente (76,47% @80%, 86,20% @90% — banda estreita demais).
Gráfico: `reports/figures/resultado_7_calibracao.png`.

---

## 14. Camada secundária: temperatura

**Decisão:** 5 features separadas — São Paulo, Rio de Janeiro, Belo Horizonte,
Brasília, Goiânia — sem ponderação entre elas. Camada secundária a partir de
2024-01-20 (primeiro dia com cobertura de 24h completas), fora do modelo principal.

**Sem vazamento por construção:** fonte é a Open-Meteo Previous Runs API
(`temperature_2m_previous_day1`), que devolve o valor previsto 24h antes do
instante válido — mesmo horizonte da previsão de carga.

**Qualidade da própria previsão de temperatura** (previsão-24h vs. reanálise ERA5,
5 cidades, jan/2024–dez/2025, 85.515 horas comparáveis): MAE agregado de 1,1102°C.

**Erro pior nas horas de pico de carga:** MAE por hora mínimo às 09h (0,8616°C),
máximo às 19h (1,4240°C) — a previsão de temperatura erra mais justamente na hora em
que a carga do SE/CO costuma atingir seu pico.

**ERA5 não é verdade absoluta:** é uma reanálise, não uma medição direta. Parte do
erro atribuído à previsão-24h pode ser, na verdade, divergência entre ERA5 e a
realidade física medida em estação — os números de previsão-vs-ERA5 e
ERA5-vs-estação não são somáveis nem diretamente comparáveis.

---

## 15. Reprodutibilidade

- Todo dado bruto identificado por SHA-256 em `data/raw/MANIFEST.json`, com URL e
  timestamp de download — não pelo conteúdo assumido como fixo (seção 3).
- Todo número deste documento e de `FACTS.md` é recalculado por
  [`src/gerar_facts.py`](../src/gerar_facts.py) a partir do dado bruto — reexecutar
  o script produz o mesmo arquivo, byte a byte (testado).
- Verificação independente em [`src/verificar_facts.py`](../src/verificar_facts.py),
  que relê `FACTS.md` e recalcula cada número separadamente, sem reusar as funções
  do gerador.

---

## 16. Limitações declaradas

- A comparação do efeito do DST (seção 6, item 1) não isola o efeito do DST —
  tendência de crescimento, mudança de matriz elétrica e pós-pandemia não são
  controlados.
- ERA5 não é medição direta — é reanálise (seção 14).
- A métrica de custo é um modelo declarado sob suposição explícita, não custo de
  despacho realizado (seção 12a).
- O fuso horário do CMO é um fato derivado por evidência empírica, não uma
  declaração de fonte — o próprio relatório que gerou essa evidência concluiu que o
  fuso permanece desconhecido sob critério documental estrito (seção 12d).
- A cobertura do CMO Semi-Horário para 2020–2023 não foi confirmada — esses anos
  nunca foram baixados porque a avaliação nunca precisou deles; 2024–2026 (os anos
  usados) já foram verificados ano a ano (seção 12e, FACTS.md seção J7).
- O mínimo histórico do subsistema NE (2018-03-21 16:00:00) não coincide com
  nenhuma das 9 datas de transição de DST e permanece sem explicação.
- A escolha do método de agregação do CMO (média) foi testada, mas ainda afeta 586
  horas específicas em mais de 10% cada — a métrica de custo em nível de hora
  individual é sensível a essa escolha, mesmo que o total anual não seja (seção
  12b).
- Contaminação de pré-treino do Chronos-2 não pode ser descartada por completo,
  mas foi PARCIALMENTE atacada (FACTS.md seção O): recomputando o resultado só na
  janela de origens posteriores ao release do checkpoint (proxy conservadora para
  o corte do corpus, já que a data exata não é pública), o Chronos-2 continua
  vencendo por MASE(sazonal) com margem grande sobre os outros 3 modelos — a
  vantagem não depende de ter memorizado ESTAS horas específicas (carga SE/CO).
  Isso NÃO descarta contaminação por padrões GENÉRICOS de energia/eletricidade no
  corpus de pré-treino: o relatório técnico do modelo (arXiv:2510.15821, Tabela 6)
  documenta datasets do domínio (Electricity, London Smart Meters, Buildings 900K,
  Solar, Wind Farms), mas não menciona nenhuma fonte brasileira ou do ONS — a
  ausência de menção não é prova de ausência, só de não documentação, e essa forma
  de contaminação (aprender padrões estruturais de carga por analogia, não
  memorizar os dados exatos) não é testável a partir daqui. Auditar por completo o
  corpus de pré-treino de um foundation model de terceiros não é possível; isso é
  uma limitação inerente a qualquer avaliação zero-shot desse tipo de modelo sobre
  séries públicas, não específica deste projeto.
- O projeto prevê CARGA (demanda), não despacho (oferta). A restrição operacional
  real — "oferta nunca pode ficar abaixo da demanda", sob pena de corte de carga no
  extremo — é responsabilidade do operador do sistema, não do modelo de previsão;
  nenhum modelo aqui a impõe fisicamente. O custo assimétrico (seção 12f) é a forma
  como este projeto *reconhece* que subprever é operacionalmente pior que
  superprever, penalizando mais o erro na direção que exigiria reserva rápida ou,
  no limite, corte de carga — mas isso é uma penalização na métrica de avaliação,
  não uma restrição física garantida por nenhum dos quatro modelos comparados.

### Extensões possíveis

Exploradas apenas se o dado sustentar, não prometidas:

1. **Correção (não era testável como escrita originalmente):** a formulação
   anterior perguntava se "a vantagem zero-shot dos foundation models... se
   sustenta ao cruzar a quebra do fim do DST (2019)". Isso não é testável no
   período de avaliação (2024-2026) — o Brasil parou de observar DST em 2019, então
   não há nenhuma transição de DST dentro do período avaliado (confirmado no
   diagnóstico de convergência do SARIMA, commit 0339234). A quebra de DST
   (2015-2019) só existe dentro do CONTEXTO/histórico usado pelos modelos, nunca
   como alvo de previsão em 2024-2026.

   Pergunta aberta e honesta, reformulada: **um contexto longo que atravessa a
   descontinuidade de DST (2015-2019) ajuda ou atrapalha a previsão de
   2024-2026?** — exploração possível, não prometida, valor incerto (pode não
   haver efeito detectável, já que a quebra fica "diluída" dentro de um contexto
   muito mais longo que ela).
2. **Achado confirmado** (deixou de ser extensão possível — já foi medido): o
   ranking de modelos por erro estatístico (MASE) NÃO coincide com o ranking por
   custo de despacho em CMO. No período de avaliação 2024-2026, SARIMA e o naive
   semanal trocam de posição entre as duas métricas — SARIMA tem MASE(sazonal)
   pior que o naive (1,3412 vs. 1,2732), mas custo total menor (R$ 8,40 bi vs.
   R$ 8,52 bi) — commit f87138a. Confirma que erro estatístico agregado não prevê
   custo de despacho, consistente com a concentração de custo em poucas horas de
   CMO alto (FACTS.md seção K).

---

## 17. O que a sondagem corrigiu — 5 hipóteses refutadas

1. **"`val_cargaenergiahomwmed` é `FLOAT`, como declara o dicionário."** Refutada:
   está armazenada como texto em 2015–2024.
2. **"A coluna de carga não tem valor nulo, como declara o dicionário."** Refutada:
   87 strings vazias existem no dataset inteiro.
3. **"`nom_subsistema` é uma chave estável para usar em joins."** Refutada: mudou de
   `SUDESTE` para `SUDESTE/CENTRO-OESTE` em 2026 — por isso a regra decidida usa
   `id_subsistema`, não `nom_subsistema`.
4. **"Dias de virada de horário de verão têm 23 ou 25 registros."** Refutada: em
   todo o dataset (2015–2026, 4 subsistemas), existe exatamente 1 dia irregular, e
   ele tem 0 registros — não 23 nem 25.
5. **"O CMO médio horário pode ficar negativo, já que o dicionário permite valor
   negativo."** Refutada no nível agregado por hora: 0 horas com a média horária do
   CMO do SE negativa, apesar de existirem 77 valores semi-horários negativos no
   dataset (todos no subsistema NE).
