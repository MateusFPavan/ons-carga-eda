# Setup & Reproducibility Guide

*Following the NeurIPS ML Code Completeness Checklist. Commands are copy-pasteable, paths are relative to the repo root, and version pins come from the actual `requirements.txt`. Where a step is not yet automated, it is marked `[TODO]` rather than described as if it worked.*

---

## 1. Prerequisites

- **OS:** developed and run on Windows (paths in logs are Windows); the code is plain Python with no OS-specific calls, so it should run on Linux/macOS — but this has **not been tested** on either. Treat cross-platform support as unverified, not confirmed.
- **Python:** 3.11+ recommended; developed and run on **Python 3.12.10**.
- **Hardware/GPU:** **CPU-only is sufficient.** `torch==2.13.0` runs on CPU here; no GPU required. The Chronos-2 foundation model (~120M params) runs on CPU in this project.
- **Accounts:** none. All data sources are public and keyless (ONS open data; Open-Meteo needs no API key).

## 2. Dependencies

Pinned in `requirements.txt` at the repo root. Key pins: `pandas==3.0.3`, `numpy==2.5.1`, `pyarrow==25.0.0`, `statsmodels==0.14.6`, `prophet==1.3.0`, `chronos-forecasting==2.3.1`, `torch==2.13.0`, `matplotlib==3.11.0`, `holidays==0.100`.

```bash
# from repo root
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

> Prophet pulls `cmdstanpy`/`stanio`; first import may compile the Stan backend. If install fails, see Troubleshooting.

## 3. Data access

No bulk data is committed. The repo ships **`data/raw/MANIFEST.json`** (URLs + SHA-256 + sizes) so the exact snapshot is reconstructible. See **`docs/DATA_CARD.md`** for provenance, licenses, and field-level detail.

- **Source:** ONS hourly load (`.../dataset/curva-carga-ho`), ONS CMO semi-hourly (dispatch price), and Open-Meteo `temperature_2m_previous_day1`.
- **Placement:** downloaded files live under `data/raw/` (load, CMO, and `data/raw/temperatura/`); derived files under `data/processed/`. Both are git-ignored except `MANIFEST.json`.
- **Fetch:** `run_all.py` does **not** download — it only verifies existing files against the manifest (§5). The snapshot was assembled incrementally by five scripts, each idempotent (skips a file if it already exists locally with a matching hash) and each registering into the same `data/raw/MANIFEST.json`:
  - `python src/download_raw.py` — ONS hourly load, 2015–2026 (`ANOS = range(2015, 2027)`).
  - `python src/download_custo.py` — 2024 sample of the 3 candidate dispatch-cost datasets (CMO Semi-Horário, CMO Semanal, CVU).
  - `python src/download_custo_cmo_2025_2026.py` — CMO Semi-Horário for 2025–2026, extending the cost coverage.
  - `python src/download_temperatura_era5.py` — ERA5 reanalysis + day-ahead forecast temperature, 5 capitals, Jan/2024–Dec/2025.
  - `python src/download_temperatura_fev_jul2026.py` — extends the temperature forecast coverage to 2026-02-01+.
  - (`python src/download_temperatura_testes.py` also exists — small test-sample windows from the exploratory phase, not part of the reproducible snapshot proper, but registered in the same manifest.)
- **Bundled sample:** none — the manifest + fetch script reconstruct the full snapshot.

> **Retrospective revision:** ONS revises historical data. Re-fetching may change past values; this is detectable as a SHA-256 mismatch against `MANIFEST.json`.

## 4. Environment / config

- **No secrets, no API keys, no env vars are required** — all sources are public and keyless. Nothing sensitive is committed, and nothing needs to be.
- **Determinism:** models are run with `seed=42` and single-threaded BLAS to keep results reproducible. When running the model scripts, force single thread:

```bash
# Linux/macOS
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 python src/<model_script>.py
```

On Windows set these with `set VAR=1` before the run. Single-threading matters: Prophet's Stan optimizer is otherwise nondeterministic and the leakage self-test will report false differences.

## 5. How to reproduce

`run_all.py` is staged so that **reproducing the result is cheap and retraining is optional** — the professional pattern (cache intermediate artefacts; do not recompute hours of training to redraw a chart). Saved predictions live in `data/processed/`, so the comparison table and charts regenerate in seconds.

```bash
python run_all.py                     # DEFAULT (all-fast): data + results, ~1.5 min
python run_all.py --stage data        # data pipeline only, ~60 s
python run_all.py --stage results     # recompute tables + charts from SAVED predictions, ~29 s
python run_all.py --stage models --yes # RETRAIN all 4 models (~4 h) — optional
python run_all.py --help              # lists every stage with its cost
```

- **`data`** runs, in fixed order, aborting the whole chain on any failure or hash mismatch: (1) verify MANIFEST (SHA-256 + size vs `MANIFEST.json`); (2) `gerar_facts.py` → `reports/FACTS.md`; (3) `verificar_facts.py` (independent recomputation, nonzero exit on divergence); (4) `limpar.py` → cleaned SE/CO; (5) `gerar_features.py` (features + leakage self-test).
- **`results`** does **not** retrain: it reads the saved predictions, recomputes every metric (including an asymmetric-cost sensitivity sweep — subprevisão penalized more than superprevisão, `src/custo_assimetrico.py`), writes `reports/tabela_comparativa.csv` and `reports/tabela_custo_assimetrico.csv`/`tabela_vies_direcional.csv`, regenerates the 8 charts in `reports/figures/`, and **hard-stops if any metric diverges from already-committed numbers** (`FACTS.md`, or — for the asymmetric-cost control case (`fator_sub=1.0`) — the existing symmetric cost). If a single model's prediction file is missing, it skips that model with a warning rather than aborting.
- **`models`** retrains all four; it **refuses to run without `--yes`** (or interactive `sim`) so 4 h of training is never triggered by accident. Determinism forced (`seed=42`, single-thread).
- **`all-fast`** (default) = `data` + `results`, ~1.5 min — this is what a reviewer runs to reproduce the result without retraining.

**Temporal split (critical):** the evaluation is **walk-forward, day-ahead, sliding origin, over 2024-01-01+ — never shuffled.** Each forecast uses only history prior to its origin. A reviewer who shuffles will not reproduce these boundaries and will leak the future.

**Artefacts produced:** `reports/FACTS.md`; `reports/tabela_comparativa.csv`; `reports/tabela_custo_assimetrico.csv`; `reports/tabela_vies_direcional.csv`; cleaned/feature data in `data/processed/`; saved predictions (`chronos_previsoes.parquet`, `prophet_previsoes.parquet`, `sarima_previsoes_60d.parquet`, …); 8 charts in `reports/figures/`.

**No `models/` directory with serialized fitted-model objects — deliberate, not a gap.** Chronos-2 is zero-shot: there is no trained model to serialize, only the pretrained checkpoint (`amazon/chronos-2`, pulled from Hugging Face). SARIMA and Prophet are each **re-fit per walk-forward origin** (one model per forecast day, ~900+ fits), so there is no single "the trained model" to save — a fitted `SARIMAXResults`/`Prophet` object is a snapshot of one origin's fit, not reusable for the next day's forecast. Saving the **predictions** (`data/processed/*_previsoes.parquet`) is the correct artefact for this walk-forward design; re-running `--stage models` regenerates them deterministically (`seed=42`, single-thread) if ever needed.

## 6. Expected results

Headline metrics on the held-out temporal test period (2024-01-01+), `seed=42`, single run (deterministic — one run suffices):

| Model | MASE (seasonal) | MAPE | Dispatch cost | Coverage @90% |
|---|---|---|---|---|
| Seasonal-naive (weekly) | 1.2732 | 5.37% | R$ 8.52 bi | — |
| SARIMA | 1.3412 | 5.68% | R$ 8.40 bi | 92.5% |
| Prophet | 1.1669 | 5.00% | R$ 7.86 bi | 86.2% |
| Chronos-2 (120M, 2048h) | **0.4363** | **1.82%** | **R$ 3.01 bi** | 88.9% |

A correct Chronos-2 run reproduces MASE **0.4363** / MAPE **1.8235%** / P05–P95 coverage **88.93%** exactly; Prophet reproduces MASE ~1.167. Leakage self-tests return **0 divergences**. If your numbers differ, stop — it signals a broken split or nondeterminism.

## 7. Runtime & resources

`python run_all.py` (default, reproduces the result): **~1.5 min**. `--stage data`: ~60 s. `--stage results`: ~29 s (table/chart regeneration, plus the asymmetric-cost, error-breakdown, and contamination-window sensitivity analyses, all recomputed from saved predictions). `--stage models` (retrain, optional): **~4 h** (Prophet ~3 h Stan fit per origin; SARIMA ~80 min; Chronos-2 ~10 min). All CPU-only; peak RAM for `python run_all.py` (default, measured with `psutil` across the whole process tree — `run_all.py` spawns each stage as a subprocess): **~306 MiB** (measured before the seções L/N/O additions; order-of-magnitude estimate still holds). This is the `data`+`results` figure; `--stage models` (loading Chronos-2/torch, fitting Prophet/SARIMA) was not measured here and will be higher.

## 8. Troubleshooting

- **Prophet install/compile fails:** ensure a C++ toolchain for `cmdstanpy`; retry `pip install prophet==1.3.0`.
- **Leakage test shows differences on Prophet:** you did not force single-thread — see §4.
- **Hash mismatch in `run_all.py`:** a `data/raw/` file changed or ONS revised it; re-fetch and re-verify.
- **Numbers drift from §6:** check the split is temporal (unshuffled) and the seed is set.

## 9. Code quality (lint)

[Ruff](https://docs.astral.sh/ruff/) is configured (`pyproject.toml`, pinned `ruff==0.15.22` in `requirements.txt`, dev-only — not required to run the pipeline). Two rule categories are intentionally disabled project-wide, not silenced case by case:

- **`E501` (line too long):** many diagnostic prints and f-strings are deliberately descriptive (sanity-check messages, tables); line length isn't a real risk in this codebase.
- **`E402` (import not at top of file):** several model scripts set single-thread environment variables (`OMP_NUM_THREADS` etc.) *before* importing `numpy`/`pandas`/`prophet` — required for Prophet's Stan optimizer to be deterministic (§4). Moving those imports to satisfy the linter would break the leakage self-test's determinism.

```bash
ruff check src/ run_all.py
```

Everything else (unused imports, undefined names, basic pycodestyle) is enforced. As of this writing, `src/` is clean except for 20 flagged-and-reviewed items (11 ambiguous single-letter loop variables named `l`, 9 unused local variables) — cosmetic or genuinely dead code, none affecting correctness; left for a future pass rather than a bulk rename/delete without review.

---

## Final self-check — MUST-HAVE items

- **Pinned deps + install:** present (§2).
- **Data access:** present (§3), including the five fetch scripts by name.
- **Exact reproduce commands, ordered:** `run_all.py` fully specified with staged modes (§5); default reproduces the result in ~1.5 min from saved predictions, `--stage models` retrains. No reproducibility `[TODO]` remains.
- **Expected results & seeds/run count:** present (§6).
- **Relative paths / no committed secrets:** present (§3, §4).
- **Code quality:** ruff configured and run (§9).

**Missing/unverified, flagged inline:** non-Windows confirmation (declared untested, not invented as working).
