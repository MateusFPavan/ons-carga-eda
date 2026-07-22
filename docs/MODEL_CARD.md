---
language: pt
license: apache-2.0
tags:
  - time-series-forecasting
  - electricity-load
  - zero-shot
  - foundation-model
datasets:
  - ONS-curva-carga-horaria
  - open-meteo-temperature
base_model: amazon/chronos-2
metrics:
  - MASE
  - MAPE
  - dispatch-cost
---

# Model Card — Day-Ahead Hourly Load Forecasting for SE/CO (Chronos-2, zero-shot)

*Following the Hugging Face / Mitchell et al. standard. **Assumed output:** `docs/MODEL_CARD.md` in the project repo — not a Hugging Face Hub README, because this project does not publish a fine-tuned model; it evaluates an off-the-shelf foundation model in a comparative study. Every metric traces to `reports/FACTS.md`.*

## 1. Model summary

The chosen model is **Chronos-2 (120M), applied zero-shot** to forecast day-ahead hourly electricity load for Brazil's SE/CO subsystem. On a held-out temporal test period it reduces error and dispatch cost by a wide margin over a seasonal-naïve baseline and over tuned SARIMA and Prophet models — with no fine-tuning.

## 2. Model details

- **Architecture:** Chronos-2, a pretrained transformer-based time-series foundation model that produces probabilistic (quantile) forecasts. Used here in **zero-shot** inference — no weights were trained or fine-tuned in this project.
- **Model size / checkpoint:** `amazon/chronos-2` (~120M parameters). A smaller `chronos-2-small` (~28M) was also evaluated.
- **Version / date:** `chronos-forecasting==2.3.1`; evaluated July 2026.
- **Authors:** model by Amazon Science; this evaluation and integration by Mateus Fardin Pavan — mateusfardinpavan@gmail.com · [GitHub](https://github.com/MateusFPavan).
- **License:** Chronos-2 under Apache-2.0 (base model). This card and the study code: MIT (this study's code and documentation).
- **Base model / links:** `amazon/chronos-2` on Hugging Face; `[TODO: add paper/repo URLs]`.
- **Runs on CPU** — no GPU required.

## 3. Intended uses

- **Task:** day-ahead (24 h) forecasting of hourly load for the SE/CO subsystem, in MWmed.
- **Users:** analysts and operations/planning teams needing a short-horizon load forecast and a calibrated uncertainty band.
- **Domain:** Brazilian interconnected system (SIN), SE/CO subsystem; the pipeline generalizes to the other subsystems (N, NE, S) as a robustness check.
- **Uncertainty:** the model emits quantiles (P10/P50/P90…), suitable for reserve-margin decisions, not just a point forecast.

## 4. Out-of-scope / where it underperforms

- **Do not shuffle.** Evaluation and use assume a strict **temporal** order; random train/test splits leak the future and invalidate the metrics.
- **Horizons beyond 24 h** were not evaluated; day-ahead is the only validated horizon.
- **Regime shifts unseen in context.** The series contains three near-overlapping breaks (end of DST 2019, pandemic 2020, a data-grid change). Forecasts whose context straddles such a break are less reliable.
- **Temperature extremes / sensor gaps.** The optional temperature layer uses day-ahead *forecast* temperature for 5 capitals; it is least accurate in evening peak hours and cannot cover interior conditions of a subsystem spanning ~a third of Brazil.
- **Not realized cost.** The dispatch-cost figure is a declared model (see §8), not an operational cost guarantee.
- **Pre-training contamination cannot be excluded** (see §9) — treat "zero-shot" as "not fine-tuned here," not as "provably never seen related data."

## 5. How to use

Actual call signature, `src/modelo_chronos2.py` (winning config — no covariates):

```python
import numpy as np
from chronos import BaseChronosPipeline   # chronos-forecasting==2.3.1

pipeline = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
# context: hourly load up to the end of day D-1 (local time), last 2048 hours, float32
contexto = historico.iloc[-2048:].to_numpy(dtype="float32")
quantis, _ = pipeline.predict_quantiles(
    inputs=[{"target": contexto}],
    prediction_length=24,
    quantile_levels=[0.05, 0.1, 0.5, 0.9, 0.95],
)
arr = np.asarray(quantis[0][0])  # shape (24, 5): P05/P10/P50/P90/P95, same order as quantile_levels
p05, p10, mediana, p90, p95 = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 4]
```

Optional temperature-covariate layer (context-controlled ablation, `src/chronos_contexto_controlado.py`) — covariates are passed as `past_covariates`/`future_covariates` dicts of same-length arrays, keyed by name:

```python
past_cov = {"dst_ativo": dst_ativo_historico}
future_cov = {"dst_ativo": dst_ativo_horas_alvo}
for cidade in ["Sao_Paulo", "Rio_de_Janeiro", "Belo_Horizonte", "Brasilia", "Goiania"]:
    past_cov[f"temp_{cidade}"] = temp_historico[cidade]      # known past temperature (or forecast, leakage-safe)
    future_cov[f"temp_{cidade}"] = temp_horas_alvo[cidade]   # day-ahead forecast temperature for the 24h target

quantis, _ = pipeline.predict_quantiles(
    inputs=[{"target": target, "past_covariates": past_cov, "future_covariates": future_cov}],
    prediction_length=24,
    quantile_levels=[0.05, 0.1, 0.5, 0.9, 0.95],
)
```

## 6. Training data

**No training was performed in this project** (zero-shot). Chronos-2 was pretrained by Amazon on a large corpus that **includes energy/electricity datasets** (Electricity, London Smart Meters, Buildings 900K, Solar, Wind Farms) but, per its technical report, **no Brazilian/ONS series is mentioned**. The evaluation data — ONS hourly load and Open-Meteo temperature — is documented in full in **`docs/DATA_CARD.md`** (provenance, licenses, dictionary, missingness, splits).

## 7. Procedure (inference configuration, not training)

Since the model is zero-shot, the reproducible knobs are the **inference and evaluation configuration**, not hyperparameters of a fit:

- **Context length:** swept over 96/256/512/1024/2048 h; **2048 h** was best (monotone improvement with context — consistent with the literature).
- **Prediction length:** 24 h (day-ahead).
- **Quantiles:** P10/P50/P90 (80% interval); P05/P95 also computed for the 90% interval.
- **Point forecast:** median (P50).
- **Determinism:** `seed=42`, single-thread (`OMP/MKL/OPENBLAS/NUMEXPR/VECLIB=1`).
- **Covariates (optional layer):** `dst_active` + 5 city temperatures as future covariates, context matched across conditions.
- Full reproduction: `python run_all.py --stage models --yes` (see `docs/SETUP.md`).

## 8. Evaluation

- **Split:** held-out **temporal test period, 2024-01-01 → 2026-07-15**, walk-forward, day-ahead, sliding origin, **never shuffled**, touched once.
- **Metrics:** MASE (seasonal denominator, comparable to the load-forecasting literature), MAPE, interval calibration, and a **dispatch-cost proxy** = |error_MW| × hourly CMO × 1 h — a *declared model*, not realized cost.
- **Baseline + candidates (the whole point of the study):**

| Model | MASE (seasonal) | MAPE | Dispatch cost | Cover @90% |
|---|---|---|---|---|
| Seasonal-naïve (weekly) | 1.2732 | 5.37% | R$ 8.52 bi | — |
| SARIMA | 1.3412 | 5.68% | R$ 8.40 bi | 92.5% |
| Prophet | 1.1669 | 5.00% | R$ 7.86 bi | 86.2% |
| **Chronos-2 (2048 h)** | **0.4363** | **1.82%** | **R$ 3.01 bi** | 88.9% |

Chronos-2 cuts MASE to ~1/3 of the naïve and dispatch cost by ~65%. Its 90% interval is near-perfectly calibrated (88.9% empirical); SARIMA over-covers, Prophet mildly under.

- **Disaggregation:**
  - *Error vs cost ranking diverges* — SARIMA and the naïve swap places between the MASE ranking and the cost ranking. Aggregate error does not predict dispatch cost (cost concentrates: ~25% in the top 10% CMO hours).
  - *Temperature layer (context-controlled):* improves Chronos-2 by ~0.18 pp MAPE, concentrated in **peak/high-CMO hours**; Prophet gains more (~0.80 pp), consistent with Chronos already encoding temperature–load patterns from pretraining.
  - `[TODO: add weekday/weekend and by-season breakdowns if computed.]`

## 9. Bias, risks & limitations

- **Pre-training contamination (concrete failure mode):** if Amazon's corpus included ONS/SIN-adjacent data, "zero-shot" performance would partly reflect memorization. Not provable from public docs; documented as an open risk.
- **DST regime confound:** the observed DST effect on load is **not causally isolated** — trend, distributed-solar growth, and post-pandemic patterns are uncontrolled confounders.
- **Holiday sensitivity:** only national holidays are encoded; state/municipal holidays and atypical calendars (e.g. election days, unusual Carnaval dates) are not, so those days may forecast worse `[TODO: quantify holiday-day error]`.
- **Temperature-gap sensitivity:** the temperature layer depends on Open-Meteo forecast availability (2024-01-20+) and is least accurate in the exact evening hours where load is most expensive.
- **Cost metric is a model, not a measurement:** in zero/negative-CMO hours (physically real spillage), modeled error cost is zero by construction.
- **Retrospective data revision:** ONS revises history; a re-pulled snapshot can shift past values (detectable via `MANIFEST.json` hash).

## 10. Compute & citation

- **Compute:** CPU-only. Chronos-2 inference over the full walk-forward: ~10 min. `[TODO: energy/CO₂ footprint not measured.]`
- **Citation:** `[TODO: add Chronos-2 paper citation and this project's citation/DOI if any.]`

---

### Final self-check — MUST-HAVE items

All present: **model summary** (§1), **model details incl. architecture/version/license** (§2), **intended + out-of-scope uses** (§3–§4), **training-data reference** (§6 → `docs/DATA_CARD.md`), **procedure with key config** (§7, adapted honestly for a zero-shot model — inference config, not training hyperparameters), **evaluation naming metric + temporal split + baseline + disaggregation** (§8), **bias/risks/limitations** (§9).

`[TODO]` items flagged inline (not invented): paper URLs, weekday/season disaggregation, holiday-error quantification, compute footprint, citation.
