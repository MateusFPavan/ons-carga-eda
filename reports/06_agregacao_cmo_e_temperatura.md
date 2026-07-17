# Agregação do CMO e correlação de temperatura

Fecha duas decisões abertas de `reports/FACTS.md` (seção I) com evidência. Nenhuma
modelagem além do baseline trivial (sazonal-naive, instrumento de medição). Nenhuma
escolha de variante ou feature foi feita. Gerado em 2026-07-17.

---

# PARTE A — Integridade das semi-horas e verificação de timezone

## A1/A2. Contagem de semi-horas por hora local, CMO Semi-Horário 2024

| Subsistema | Horas com 2 semi-horas | Horas com 1 semi-hora | Horas com >2 semi-horas | Total de horas com dado |
|---|---|---|---|---|
| N | 8.688 | 0 | 0 | 8.688 |
| NE | 8.688 | 0 | 0 | 8.688 |
| S | 8.688 | 0 | 0 | 8.688 |
| SE | 8.688 | 0 | 0 | 8.688 |

Nenhuma hora com exatamente 1 semi-hora foi encontrada em nenhum dos 4 subsistemas —
lista de horas com 1 semi-hora: vazia. Nenhuma hora com mais de 2 semi-horas foi
encontrada — lista: vazia.

Subsistema SE, horas com **0** semi-horas (buraco de hora inteira, dentro do
calendário do ano): **96** de 8.784 horas esperadas (366 dias × 24h). 96 ÷ 24 = 4 —
consistente com os 4 dias inteiramente ausentes já registrados em `reports/FACTS.md`
(2024-02-08, 02-17, 07-13, 12-29). Nenhuma hora parcial (1 de 2 semi-horas) existe
fora desses 4 dias.

## A3. Verificação de timezone do CMO — medida, não assumida

**Método:** comparado o perfil horário médio do CMO (subsistema SE, 2024, rótulo de
hora exatamente como armazenado no arquivo, sem nenhuma conversão) contra o perfil
horário médio da carga (SE/CO, 2024, mesma base). Testada a correlação entre os dois
perfis de 24 pontos para toda defasagem (lag) possível de um ciclo diário completo,
de -12h a +12h, usando deslocamento circular (`numpy.roll`).

**Perfil horário médio do CMO (SE, 2024, R$/MWh):**

| Hora | CMO | Hora | CMO |
|---|---|---|---|
| 00h | 102,17 | 12h | 81,96 |
| 01h | 99,39 | 13h | 85,58 |
| 02h | 98,53 | 14h | 91,16 |
| 03h | 98,25 | 15h | 101,24 |
| 04h | 98,41 | 16h | 124,40 |
| 05h | 98,78 | 17h | 136,50 |
| 06h | 96,38 | **18h** | **171,02** |
| 07h | 91,41 | 19h | 158,17 |
| 08h | 86,34 | 20h | 138,71 |
| 09h | 82,73 | 21h | 135,58 |
| **10h** | **81,86** | 22h | 128,41 |
| 11h | 82,09 | 23h | 112,18 |

Pico do CMO: **18h** (171,02 R$/MWh). Vale do CMO: **10h** (81,86 R$/MWh).
Pico da carga SE/CO: **19h**. Vale da carga SE/CO: **04h**.

**Correlação perfil CMO × perfil carga, por defasagem (lag), ciclo completo de 24h:**

| Lag (h) | r | Lag (h) | r |
|---|---|---|---|
| -12 | -0,3331 | +1 | 0,3509 |
| -11 | -0,0622 | +2 | 0,1992 |
| -10 | 0,1830 | +3 | -0,0051 |
| -9 | 0,3769 | +4 | -0,2509 |
| -8 | 0,5121 | +5 | -0,5036 |
| -7 | 0,5788 | +6 | -0,7270 |
| **-6** | **0,5942** | +7 | -0,8819 |
| -5 | 0,5908 | +8 | -0,9461 |
| -4 | 0,5786 | +9 | -0,9139 |
| -3 | 0,5616 | +10 | -0,7895 |
| -2 | 0,5306 | +11 | -0,5876 |
| -1 | 0,4939 | +12 | -0,3331 |
| 0 | 0,4501 | | |

Máximo do ciclo completo: **lag = -6h** (r = 0,5942). No lag = 0 (nenhum deslocamento,
rótulos comparados como estão): r = 0,4501.

**Comparação direta com a hipótese específica de deslocamento UTC↔local de 3 horas:**
se o CMO estivesse armazenado em UTC e precisasse de +3h para virar hora local
(UTC-3), o deslocamento que corrigiria isso produziria o melhor alinhamento em
lag = +3h. O valor medido em lag = +3h é **r = -0,0051** — pior que em lag = 0
(r = 0,4501), não melhor. Em lag = -3h, r = 0,5616 — moderadamente melhor que lag = 0,
mas não é o máximo do ciclo (que fica em -6h, não em ±3h).

**Fato registrado, sem interpretação além do que os números mostram:** nenhum pico
nítido e isolado em lag = ±3h foi encontrado que sustentasse, de forma decisiva, a
hipótese específica "CMO está em UTC e precisa de correção de 3h". O deslocamento
que corrige especificamente para essa hipótese (lag = +3h) piora a correlação em vez
de melhorá-la. O máximo do ciclo completo está em lag = -6h, um valor que não
corresponde a nenhuma hipótese de fuso horário testável (não há fuso com defasagem de
6h em relação ao Brasil relevante aqui). Este teste não prova que o CMO está em hora
local — ele não revela evidência de que o CMO esteja em UTC. As formas dos dois
perfis (CMO com vale ao meio-dia e pico às 18h; carga com vale às 4h e pico às 19h)
são estruturalmente diferentes uma da outra, o que limita a capacidade de um teste de
correlação-por-defasagem de isolar uma hipótese de fuso horário de forma limpa.

**Decisão de prosseguir:** como o teste não revelou evidência de que o CMO esteja em
UTC (condição de parada da tarefa), a Parte B foi executada.

---

# PARTE B — Sensibilidade da métrica de custo à agregação

Sazonal-naive: previsão(H, D) = observado(H, D−7). Instrumento de medição, não é o
modelo do projeto. Carga de 2023 (dez) usada apenas para permitir o naive nos
primeiros 7 dias de 2024 — os erros reportados são só de 2024.

**Confirmação:** 0 dos 9 timestamps de `is_dst_transition` (2015–2019) caem em 2024.

## B1. Como cada variante trata as semi-horas

Como a Parte A não encontrou nenhuma hora com exatamente 1 semi-hora (0 de 8.688),
as três variantes — média, máximo, primeira semi-hora — são calculadas sobre
exatamente 2 valores em 100% das horas com dado. Nenhuma hora foi afetada por uma
regra especial de "hora com 1 valor" porque essa situação não ocorre na amostra.

## B4. Métrica estatística do naive, 2024 inteiro (contexto, não é o teste)

| Métrica | Valor |
|---|---|
| N horas (métrica estatística) | 8.784 |
| MAPE | 5,4618% |
| RMSE | 3.295,53 MW |
| MAE | 2.410,14 MW |

N horas na métrica de custo (excluindo os 4 dias sem CMO): **8.688**, vs. **8.784**
na métrica estatística — diferença de 96 horas, as mesmas 4 dias × 24h da Parte A.

## B2/B3. Custo por variante e diferença entre variantes

| Variante | Custo total (R$) | Custo médio por hora (R$) | Custo mediano por hora (R$) |
|---|---|---|---|
| (a) Média das 2 semi-horas | 2.046.650.092,91 | 235.572,06 | 12.437,93 |
| (b) Máximo das 2 semi-horas | 2.102.879.656,47 | 242.044,16 | 12.691,78 |
| (c) Primeira semi-hora | 2.034.348.416,26 | 234.156,13 | 12.256,84 |

- Custo total de (b) como % de (a): **102,7474%**
- Custo total de (c) como % de (a): **99,3989%**

**Correlação entre as três séries horárias de custo:**

| Par | r |
|---|---|
| (a) média × (b) máximo | 0,993299 |
| (a) média × (c) primeira | 0,990839 |
| (b) máximo × (c) primeira | 0,975031 |

**Horas em que a variante muda o custo em mais de 10% em relação a (a):**

| Comparação | N horas | % de 8.688 |
|---|---|---|
| (b) vs. (a) | 586 | 6,7439% |
| (c) vs. (a) | 586 | 6,7439% |

**Fato verificado:** o conjunto de 586 horas é **exatamente o mesmo** nas duas
comparações — não apenas a mesma contagem por coincidência, confirmado comparando os
índices de hora diretamente (interseção = 586, diferença em ambas as direções = 0).

## B5. Efeito de CMO zero e negativo

| Item | Valor |
|---|---|
| Horas de 2024 (SE, dentro da métrica de custo) com CMO médio == 0 | 1.084 |
| Erro médio absoluto do naive nessas horas | 3.041,29 MW |
| Horas com CMO médio < 0 | **0** |
| Erro médio absoluto do naive nessas horas | N/A (nenhuma hora) |
| MAE geral do naive, 2024 (para comparação) | 2.410,14 MW |

**Fato:** embora existam 77 valores semi-horários negativos na amostra de 2024
(`reports/05_sondagem_custo.md`), **nenhuma hora com a média das 2 semi-horas sai
negativa** — os semi-horários negativos sempre têm seu par (mesma hora) positivo o
suficiente para que a média não cruze zero.

| Item | Valor |
|---|---|
| Limiar do decil 90 do CMO médio horário (SE, 2024) | 359,87 R$/MWh |
| N horas no top 10% de CMO | 869 de 8.688 |
| % do custo total do ano (variante média) vindo dessas 869 horas | **47,2269%** |

---

# PARTE C — Correlação de temperatura entre as 5 capitais

## C1. Matriz de correlação entre as 5 cidades (`previous_day1`, jan/2024–dez/2025)

| | São Paulo | Rio de Janeiro | Belo Horizonte | Brasília | Goiânia |
|---|---|---|---|---|---|
| **São Paulo** | 1,0000 | 0,8991 | 0,7827 | 0,6834 | 0,7066 |
| **Rio de Janeiro** | 0,8991 | 1,0000 | 0,7892 | 0,6571 | 0,6467 |
| **Belo Horizonte** | 0,7827 | 0,7892 | 1,0000 | 0,8844 | 0,8617 |
| **Brasília** | 0,6834 | 0,6571 | 0,8844 | 1,0000 | 0,9413 |
| **Goiânia** | 0,7066 | 0,6467 | 0,8617 | 0,9413 | 1,0000 |

Maior correlação entre pares: Brasília × Goiânia (0,9413). Menor: Rio de Janeiro ×
Goiânia (0,6467).

## C2. Correlação de cada cidade com a carga SE/CO (2024-01-20 em diante)

Correlação descritiva — não usada aqui para selecionar nenhuma cidade.

| Cidade | N horas comparáveis | Correlação com carga SE/CO |
|---|---|---|
| São Paulo | 17.088 | 0,6059 |
| Rio de Janeiro | 17.088 | 0,6109 |
| Belo Horizonte | 17.088 | 0,6461 |
| Brasília | 17.088 | 0,5636 |
| Goiânia | 17.088 | 0,5698 |

## C3. Cobertura simultânea

| Item | Valor |
|---|---|
| Horas com dado nas 5 cidades simultaneamente | 17.103 |
| Horas com dado em pelo menos 1 cidade | 17.103 |
| Horas totais na grade (união de timestamps, jan/2024–dez/2025) | 17.544 |

**Fato:** os dois primeiros números são idênticos (17.103) — em toda hora em que
qualquer uma das 5 cidades tem valor não-nulo de `previous_day1`, as 5 têm. Não há
hora em que algumas cidades tenham dado e outras não, na amostra baixada.

---

## Reprodutibilidade

- Ambiente: Python 3.12.10, `numpy`, `pandas`, dependências pinadas em
  [`requirements.txt`](../requirements.txt).
- Scripts: [`src/probe_cmo_integridade.py`](../src/probe_cmo_integridade.py) (Parte A),
  [`src/probe_sensibilidade_custo.py`](../src/probe_sensibilidade_custo.py) (Parte B),
  [`src/probe_correlacao_temperatura.py`](../src/probe_correlacao_temperatura.py) (Parte C).
- Saídas intermediárias: [`data/interim/probe_cmo_integridade.json`](../data/interim/probe_cmo_integridade.json),
  [`data/interim/probe_sensibilidade_custo.json`](../data/interim/probe_sensibilidade_custo.json),
  [`data/interim/probe_correlacao_temperatura.json`](../data/interim/probe_correlacao_temperatura.json).
- Nenhum download novo. Nenhum arquivo em `data/raw/` foi alterado. Nenhuma variante
  de agregação do CMO nem nenhuma cidade de temperatura foi escolhida — só medido e
  reportado, conforme restrição.
