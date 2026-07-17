# Fuso horário do CMO Semi-Horário

Investigação isolada: em qual fuso horário estão os timestamps do CMO Semi-Horário.
Nenhuma análise nova de custo, nenhuma decisão. O relatório 06 tentou inferir o fuso
por correlação CMO × carga com defasagem; o teste não produziu um pico correspondente
a nenhuma hipótese de fuso testável (pico em -6h). Este relatório troca de
instrumento e vai à fonte primária. Gerado em 2026-07-17.

---

## 1. Dicionário de dados do CMO Semi-Horário — transcrição literal

Arquivo: `data/raw/documentacao/DicionarioDados_Cmo_Semi_Horario.pdf` (baixado nesta
sessão; não estava em disco antes — registrado em `data/raw/MANIFEST.json`, URL
`https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/cmo_tm/DicionarioDados_Cmo_Semi_Horario.pdf`,
SHA-256 `1794ee35942e2f52...`, 169.640 bytes). Documento datado de 02-05-2023, versão
1.2.

Transcrição literal da linha da coluna de tempo:

> Data de referência | din_instante | DATETIME | YYYY-MM-DD HH:MM:SS | Não | ---- | ----

Colunas da tabela, nesta ordem: Descrição, Código, Tipo de Dado, Formato, Permite
valor nulo, Permite valor zerado, Permite valor negativo.

**O documento inteiro (2 páginas, incluindo a descrição geral do dado e o histórico de
versões) não contém, em nenhum lugar, as palavras "fuso", "UTC", "Brasília", "local"
ou qualquer variação.** Nenhuma menção a fuso horário foi encontrada.

Descrição geral do dado (para contexto, também sem menção a fuso):

> "Valores do custo, por unidade de energia produzida, para atender ao incremento de
> uma unidade de carga no SIN, chamado de Custo Marginal de Operação – CMO. Este CMO é
> estimado pelo modelo DESSEM para cada barra do sistema em base semi-horária. O CMO
> do subsistema é obtido pelo média dos CMOs nas barras de cada subsistema, ponderados
> pelas respectivas cargas, considerando que um aumento de carga no subsistema se dá
> de maneira uniforme nas barras que a ele pertencem."

---

## 2. Dicionário de dados da Curva de Carga Horária — transcrição literal, para comparação

Arquivo: `data/raw/documentacao/DicionarioDados_CurvaCarga.pdf` (baixado nesta sessão,
não estava em disco antes — registrado no MANIFEST, URL
`https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/curva-carga-ho/DicionarioDados_CurvaCarga.pdf`,
SHA-256 `ba0fb840656b8cd0...`, 283.974 bytes). Documento datado de 06-04-2026, versão
1.2.

Transcrição literal da linha da coluna de tempo:

> Data de referência | din_instante | DATETIME | YYYY-MM-DD HH:MM:SS | Não | ---- | ----

**Idêntica, campo a campo, à linha correspondente do dicionário do CMO** (mesmo nome
de campo, mesmo tipo, mesmo formato, mesma frase "Data de referência"). Este documento
também não contém, em nenhum lugar, as palavras "fuso", "UTC", "Brasília", "local" ou
qualquer variação.

**Fato:** nenhum dos dois dicionários declara o fuso horário da coluna `din_instante`.
Os dois usam exatamente a mesma frase e o mesmo formato para descrever essa coluna,
sem diferenciação entre os dois datasets. Isso não prova que os dois sigam a mesma
convenção de fuso — apenas que a documentação, onde existe, é idêntica e omissa nos
dois casos.

---

## 3. Documentação geral do portal — busca e resultado

Páginas verificadas:

| Página | URL | Resultado |
|---|---|---|
| Página inicial do portal | `https://dados.ons.org.br/` | Sem link para FAQ, glossário, metodologia ou convenção de fuso. Menu: Conjuntos de dados, Organizações, Grupos, Sobre. |
| Página "Sobre" | `https://dados.ons.org.br/about` | Fala dos princípios de dados abertos e da organização ONS. Nenhuma menção a fuso horário, UTC, "hora de Brasília" ou "horário local". |
| Repositório GitHub `ONSBR/DadosAbertos` (linkado na página inicial) | `https://github.com/ONSBR/DadosAbertos` | Repositório colaborativo de notebooks de análise, não de documentação de dados. Nenhuma menção a fuso horário no README. |
| Página do CMO no site institucional do ONS (linkada como "Source" no dataset) | `http://www.ons.org.br/paginas/energia-amanha/cmo-semi-horario/cmo-semi-horário` | Página de dashboard dinâmico (com placeholders `{{...}}` não preenchidos na versão obtida). Nenhuma menção a fuso horário. |

**Metadados administrativos do próprio portal (não é o dicionário de dados; é a ficha
CKAN do dataset):** as páginas de dataset (`/dataset/cmo-semi-horario` e
`/dataset/curva-carga`) mostram campos "Última atualização" e "Criado em" com o
sufixo **"(BRT)"** — por exemplo, "julho 17, 2026, 12:01 (BRT)". Este sufixo é
**idêntico, incluindo o valor exato**, nas páginas dos dois datasets (mesma data e
hora em ambos). Isso indica uma convenção genérica do portal (provavelmente do próprio
software CKAN, ou de um template compartilhado) para exibir QUANDO o arquivo foi
publicado/atualizado no portal — não é uma declaração sobre o fuso horário da coluna
`din_instante` dentro dos arquivos de dado. Registrado aqui porque foi encontrado,
não porque responda a pergunta.

**Nenhuma página de documentação geral, FAQ ou metodologia sobre convenção de fuso
horário nos datasets foi encontrada no portal.**

---

## 4. Teste independente — CMO Semi-Horário agregado por semana vs. CMO Semanal

**Convenção de semana confirmada:** os 3 primeiros valores de `din_instante` do CMO
Semanal (SE, 2024) caem todos numa sexta-feira (2024-01-05, 2024-01-12, 2024-01-19).
Isso bate com `dat_fimsemana` do CVU das Usinas Térmicas (sondagem 05), que também usa
sexta-feira como fim da semana operativa. A janela usada para cada semana foi definida
como `[din_instante − 6 dias 00:00:00, din_instante 23:59:59]` (sábado 00:00 a sexta
23:59).

**Método:** para cada uma das 52 semanas do CMO Semanal (SE), filtrada e calculada a
média dos registros do CMO Semi-Horário (SE) dentro da janela da semana, comparada
contra o valor declarado em `val_cmomediasemanal`. Repetido com um deslocamento de
+3h e de -3h aplicado aos timestamps do Semi-Horário antes de filtrar.

| Deslocamento aplicado | N semanas | Diferença média (semi − semanal) | Diferença média ABSOLUTA | Diferença máxima absoluta |
|---|---|---|---|---|
| 0h (nenhum) | 52 | 7,212748 | 9,717605 | 126,242887 |
| +3h | 52 | 7,212802 | 9,499179 | 120,632560 |
| -3h | 52 | 7,222805 | 9,989611 | 124,551518 |

Amostra da tabela semana a semana (deslocamento 0h):

| Semana (fim) | N registros semi-horário na janela | Média semi-horário | CMO Semanal declarado | Diferença |
|---|---|---|---|---|
| 2024-01-05 | 240 (semana truncada — sem dado antes de 2024-01-01) | 0,0033 | 0,00 | 0,0033 |
| 2024-01-12 | 336 | 9,3272 | 0,00 | 9,3272 |
| 2024-01-19 | 336 | 3,8711 | 0,00 | 3,8711 |
| 2024-01-26 | 336 | 0,0149 | 0,00 | 0,0149 |
| 2024-02-02 | 336 | 0,0274 | 0,00 | 0,0274 |
| 2024-02-09 | 288 (falta 1 dia — 2024-02-08, já registrado em FACTS.md) | 0,0038 | 0,00 | 0,0038 |
| ... | | | | |
| 2024-12-13 | 336 | 11,5834 | 5,49 | 6,0934 |
| 2024-12-20 | 336 | 1,6482 | 1,71 | -0,0618 |
| 2024-12-27 | 336 | 2,0887 | 2,69 | -0,6013 |

**Fatos observados:**

- A contagem de registros por semana (336 = 7×48) confirma internamente a janela
  usada: as duas semanas com contagem menor (240 e 288) correspondem exatamente aos
  dias já sabidos como ausentes no CMO Semi-Horário (2024-01-01 é o início do
  arquivo; 2024-02-08 é um dos 4 dias inteiramente ausentes).
- A diferença entre a média do Semi-Horário e o valor declarado do Semanal varia em
  magnitude (de 0,002 a 126,24) e em SINAL (positiva e negativa) de semana para
  semana — não há um viés direcional constante.
- **O deslocamento de 3h não muda materialmente o resultado:** diferença média
  absoluta = 9,72 (0h), 9,50 (+3h), 9,99 (-3h) — variação de menos de 3% entre as três
  versões, muito menor que a magnitude da diferença já existente sem deslocamento
  nenhum.

**Este teste é INCONCLUSIVO para determinar o fuso horário**, pelos motivos previstos
na própria tarefa: 3 horas são uma fração pequena (1,8%, ou 6 de 336 registros) de uma
janela semanal de 168 horas, e o deslocamento não produz uma mudança detectável na
métrica de diferença. Adicionalmente, a magnitude e o sinal variável das diferenças
entre as duas fontes — mesmo sem nenhum deslocamento — são consistentes com o fato de
que os dois datasets vêm de modelos diferentes (CMO Semanal é resultado do DECOMP,
modelo de planejamento da operação; CMO Semi-Horário é resultado do DESSEM, modelo de
despacho de curtíssimo prazo — ver descrições de cada dicionário), o que por si só já
explicaria discrepância entre os dois sem que isso tenha relação com fuso horário.
Este teste não isola um sinal de fuso horário de um sinal de diferença metodológica
entre modelos.

---

## 5. Teste estrutural — perfil intradiário do CMO (SE, 2024)

| Hora | CMO médio (R$/MWh) | Hora | CMO médio (R$/MWh) |
|---|---|---|---|
| 00h | 102,1654 | 12h | 81,9569 |
| 01h | 99,3905 | 13h | 85,5775 |
| 02h | 98,5336 | 14h | 91,1575 |
| 03h | 98,2519 | 15h | 101,2441 |
| 04h | 98,4061 | 16h | 124,4039 |
| 05h | 98,7846 | 17h | 136,5028 |
| 06h | 96,3822 | **18h** | **171,0205** |
| 07h | 91,4139 | 19h | 158,1735 |
| 08h | 86,3389 | 20h | 138,7098 |
| 09h | 82,7290 | 21h | 135,5829 |
| **10h** | **81,8598** | 22h | 128,4098 |
| 11h | 82,0940 | 23h | 112,1847 |

Hora do máximo: **18h** (171,0205). Hora do mínimo: **10h** (81,8598). Amplitude
(máximo − mínimo): 89,1608. Média geral das 24 horas: 107,5531. Coeficiente de
variação entre horas (desvio padrão ÷ média): 0,2339.

**O perfil não é plano** — há uma diferença de ~2,1× entre a hora de maior e a de
menor CMO médio, com um vale entre 09h-13h e um pico concentrado em 17h-21h. Isso, por
si só, **não determina o fuso horário**: o formato do perfil (vale ao redor do meio-dia,
pico no início da noite) é compatível com características conhecidas de sistemas
hidrotérmicos com geração solar relevante, independentemente de qual seja o rótulo de
fuso horário usado para as horas — um perfil com essa forma apareceria de qualquer
jeito, esteja a hora rotulada em UTC ou em horário local, apenas com os números de
hora diferentes. Este teste não distingue, sozinho, entre as duas hipóteses de fuso.

---

## 6. Resposta exigida

**(c) O fuso horário dos timestamps do CMO Semi-Horário permanece DESCONHECIDO.**

Resumo do que foi verificado e não resolveu a questão:

- O dicionário de dados do CMO Semi-Horário não declara fuso horário em nenhum lugar
  do documento (seção 1).
- O dicionário de dados da Curva de Carga Horária, usado para comparação, também não
  declara fuso horário — os dois documentos usam a mesma frase, sem diferenciação
  (seção 2).
- Nenhuma página de documentação geral do portal ONS (página inicial, "Sobre",
  repositório GitHub colaborativo, página institucional do CMO) contém uma declaração
  de convenção de fuso horário. O único uso do rótulo "(BRT)" encontrado é nos
  metadados administrativos do portal (data de publicação do arquivo no CKAN), que é
  idêntico entre datasets diferentes e não se refere à coluna `din_instante` dentro
  dos dados (seção 3).
- O teste de correlação CMO × carga com defasagem, no relatório 06, não produziu um
  pico correspondente a nenhuma hipótese de fuso testável.
- O teste de agregação semanal do CMO Semi-Horário comparado ao CMO Semanal, nesta
  sondagem, é inconclusivo: um deslocamento de 3 horas não muda materialmente o
  resultado, e a diferença de base entre as duas fontes já é grande e de sinal
  variável antes de qualquer deslocamento — provavelmente por diferença de modelo
  (DECOMP vs. DESSEM), não por fuso horário (seção 4).
- O perfil intradiário do CMO tem formato não-plano, mas essa forma não permite, por
  si só, inferir o rótulo de fuso horário das horas (seção 5).

---

## Reprodutibilidade

- Ambiente: Python 3.12.10, `pandas`, dependências pinadas em
  [`requirements.txt`](../requirements.txt).
- Scripts: [`src/probe_fuso_cmo.py`](../src/probe_fuso_cmo.py) (seções 4 e 5).
- Dicionários baixados nesta sessão (não estavam em `data/raw/` antes) e registrados em
  `data/raw/MANIFEST.json`: `data/raw/documentacao/DicionarioDados_Cmo_Semi_Horario.pdf`,
  `data/raw/documentacao/DicionarioDados_CurvaCarga.pdf`.
- Saída intermediária: [`data/interim/probe_fuso_cmo.json`](../data/interim/probe_fuso_cmo.json).
- Nenhum outro arquivo em `data/raw/` foi alterado. Nenhum CAPTCHA foi contornado,
  nenhuma autenticação foi feita.
