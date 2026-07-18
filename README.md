# ons-carga-eda

Previsão day-ahead (24h à frente) da carga elétrica horária do subsistema SE/CO,
usando o dado público de Curva de Carga Horária do ONS. O objetivo final é também
traduzir o erro de previsão em custo, usando o preço marginal de operação (CMO) do
próprio SIN como referência.

## Status: EM CONSTRUÇÃO

Sondagem e escopo concluídos. **Nenhum modelo foi treinado ou avaliado ainda** —
o único número de erro que existe no repositório vem do sazonal-naive, usado como
instrumento de medição durante a sondagem (não como resultado do projeto).

## Como reproduzir

```
pip install -r requirements.txt
python run_all.py
```

`run_all.py` não baixa nada da internet. Ele verifica a integridade do que já está
em `data/raw/` contra os hashes SHA-256 gravados em `data/raw/MANIFEST.json` e depois
roda, em ordem, a geração de fatos, a limpeza e a geração de features. Os arquivos de
dado bruto em si (`data/raw/*.parquet`, `data/raw/temperatura/*`, `data/raw/custo/*`)
não estão neste repositório — só o manifesto que os identifica.

## Estrutura

- [`reports/FACTS.md`](reports/FACTS.md) — fonte única de números do projeto. Todo
  valor é gerado por código ([`src/gerar_facts.py`](src/gerar_facts.py)) a partir do
  dado bruto; nenhum número é digitado à mão. Verificação independente em
  [`src/verificar_facts.py`](src/verificar_facts.py).
- [`reports/ESCOPO.md`](reports/ESCOPO.md) — decisões de escopo travadas com
  evidência (alvo, horizonte, tratamento de horário de verão, validação, métrica de
  custo).
- `reports/00_*.md` a `reports/07_*.md` — relatórios de sondagem, na ordem em que
  foram escritos. Não são reescritos depois de fechados; divergências entre um
  relatório de sondagem e uma decisão posterior ficam registradas, não apagadas.
- `src/` — scripts de geração (`gerar_facts.py`, `limpar.py`, `gerar_features.py`),
  scripts de sondagem (`probe_*.py`) e download (`download_*.py`).

## Dados e licenças

- **ONS — Curva de Carga Horária.** Licença CC-BY, declarada pelo portal de dados
  abertos do ONS. `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/curva-carga-ho`
- **ONS — CMO Semi-Horário.** Licença CC-BY. `https://dados.ons.org.br/dataset/cmo-semi-horario`
- **Open-Meteo — Previous Runs API** (camada secundária de temperatura, ainda fora
  do modelo principal). Licença CC BY 4.0, sem chave de acesso.

Detalhes de proveniência (hash do snapshot, datas de download, divergências entre o
dado observado e o dicionário oficial) estão em `reports/FACTS.md` seção A e seção 8
de `reports/ESCOPO.md`.
