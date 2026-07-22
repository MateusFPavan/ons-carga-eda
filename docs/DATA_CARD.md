# Data Card — Hourly Electricity Load (SE/CO Subsystem, Brazil) with Exogenous Features

*Following Gebru et al., "Datasheets for Datasets." Every quantitative claim below traces to `reports/FACTS.md`, the project's canonical facts sheet, which is regenerated from raw files by `src/gerar_facts.py` (no hand-typed numbers). Where a fact is not established, it is marked `[TODO]` rather than invented.*

---

## 1. Motivation

**Why does this dataset exist?** It was assembled to support a day-ahead hourly electricity-load forecasting study for the Southeast/Center-West (SE/CO) subsystem of the Brazilian National Interconnected System (SIN), and to compare classical time-series models against a zero-shot time-series foundation model, evaluated not only by statistical error but by a dispatch-cost proxy.

**Who created the underlying data, and who assembled this dataset?** The primary series are published by the **Operador Nacional do Sistema Elétrico (ONS)**, Brazil's grid operator, through its open-data portal. Temperature comes from **Open-Meteo** (ERA5-based reanalysis and archived past forecasts). This project did not generate any measurements; it downloaded, versioned, cleaned, and joined public series. The assembly, cleaning, and feature construction are the author's.

**Funding.** No external funding; a personal portfolio project. `[TODO: confirm no institutional affiliation to declare.]`

---

## 2. Composition

**What is an instance?** One hourly observation of electricity load for one subsystem, indexed by local timestamp (America/São_Paulo). The modeling target is the SE/CO subsystem.

**How many instances?** The SE/CO load series has **101,136 hourly rows**, spanning **2015-01-01 00:00 to 2026-07-15 23:00**. Three sibling subsystems (N, NE, S) are retained for robustness checks (N has 101,112 rows — one full missing day; the others 101,136).

**What does the target mean?** `val_cargaenergiahomwmed` — the hourly mean electricity load in **MWmed (average MW over the hour)**. For SE/CO, over 101,108 valid values: min **21,299.35** (2015-06-28 07:00), max **62,149.89** (2025-02-18 14:00), mean **39,075.43**, median **39,046.66**, std **6,633.63**, Q25 **34,216.18**, Q75 **43,613.86**.

**Exogenous features.**
- **Calendar** (deterministic, derived from the timestamp): hour of day, day of week, month, holiday flag, and a daylight-saving-time regime flag (`is_dst_transition` for the 9 special timestamps; a DST-active indicator for the pre-2019 regime).
- **Temperature** (secondary layer, 2024+ only): `temperature_2m_previous_day1` from Open-Meteo — the day-ahead *forecast* value, not the observed value, to avoid leakage — for 5 capitals (São Paulo, Rio de Janeiro, Belo Horizonte, Brasília, Goiânia), kept as 5 separate features.

**Temporal splits (do NOT shuffle).** Evaluation is walk-forward, day-ahead, sliding origin, over **2024-01-01 to 2026-07-15**, touched once. Training uses all history prior to each forecast origin. The temperature-augmented comparison is restricted to **2024-01-20+** (first day with complete 24-hour forecast coverage). The test set is never used for any decision.

**Missing data.** The load target has **87 empty strings** across 2015–2024 (a column the official dictionary declares non-nullable). For SE/CO specifically: 24 missing on 2015-04-09 and 4 daylight-saving-transition gaps in October, none imputed. See §4.

**Does it sample a larger set?** It is the complete published SE/CO series for the window, not a sample. CMO (dispatch price) was verified in detail only for 2024; 2020–2023 and 2025–2026 coverage is asserted by the portal listing, not year-by-year verified `[TODO: verify CMO 2020–2023, 2025–2026]`.

**Sensitive / confidential content?** None. These are aggregate grid measurements and weather; no personal data, no individuals.

### Data dictionary

| Column | Type | Description | Example | % missing |
|---|---|---|---|---|
| `din_instante` | datetime (local, America/São_Paulo) | Hourly timestamp; the index. Not shuffled. | `2025-02-18 14:00:00` | 0% |
| `id_subsistema` | string | Subsystem code; join key (never `nom_subsistema`, which changed in 2026). | `SE` | 0% |
| `val_cargaenergiahomwmed` | float (MWmed) | **Target** — hourly mean load. | `62149.885` | ~0.03% (28 of 101,136 for SE) |
| `temp_<city>` (×5) | float (°C) | Day-ahead forecast temperature per capital; leakage-safe. | `24.3` | 0% within 2024-01-20+ coverage |
| `hora` | int (0–23) | Hour of day (calendar). | `14` | 0% |
| `dia_semana` | int (0–6) | Day of week. | `1` | 0% |
| `mes` | int (1–12) | Month. | `2` | 0% |
| `is_feriado` | bool | National holiday flag. | `false` | 0% |
| `is_dst_transition` | bool | One of the 9 DST-transition timestamps; excluded as forecast origin. | `false` | 0% |

---

## 3. Collection process

**How acquired?** Programmatic download from the ONS open-data S3 endpoint (`.../dataset/curva-carga-ho`) and the Open-Meteo Previous Runs API. No scraping of protected pages, no authentication bypass.

**Time range & resolution.** Load: hourly, 2015–2026. Temperature: hourly, day-ahead forecast, 2024-01-20 onward (usable). CMO dispatch price: 30-minute native, 2024 verified.

**When?** The load snapshot was downloaded **2026-07-16**, recorded by SHA-256 in `MANIFEST.json`. This matters because ONS runs a "recurring consistency process" that revises data retrospectively — 2015–2024 files share a single batch `Last-Modified` date (2025-10-09), so the series is **not immutable**; the snapshot is identified by hash rather than assumed fixed.

**Ethics/consent.** Not applicable — no human subjects; aggregate grid and weather data under open licenses.

---

## 4. Preprocessing / cleaning / feature construction

- **Type coercion:** `val_cargaenergiahomwmed` is stored as **text in 2015–2024, float in 2025–2026** (a dictionary divergence). Converted to float with a round-trip check; suppressed trailing zeros are not treated as precision loss. The same text-in-recent-year pattern appears in CMO's `val_cmo` (2026).
- **Key discipline:** `id_subsistema` is the join key; `nom_subsistema` is never used (it changed from `SUDESTE` to `SUDESTE/CENTRO-OESTE` in 2026 while the code `SE` stayed constant).
- **Missing values:** empty strings → NaN, **not imputed**. The 4 October DST gaps are left as NaN because imputing would invent load for an hour that (in local time) did not occur.
- **DST transitions:** the 9 special timestamps (4 nonexistent local hours, 5 ambiguous) are flagged and **excluded as forecast origins**, generated via `zoneinfo`/IANA, not hardcoded.
- **Calendar features:** derived deterministically from the timestamp.
- **Temperature features:** aligned by local timestamp; the leakage-safe `previous_day1` value is used, never the observed same-day temperature.
- **CMO aggregation:** 30-min → hourly by **mean of the two half-hours** (tested against max and first-half-hour; total-cost difference small).
- **Retained raw data:** all raw parquet is kept and hash-versioned; `MANIFEST.json` reconstructs the snapshot.
- **Excluded and why:** CVU and weekly-CMO datasets were dropped (would require merit-order modeling / insufficient granularity). Pre-2020 CMO does not exist, so the cost metric applies only to the test period.

---

## 5. Uses

**Intended.** Day-ahead hourly load forecasting for SE/CO; comparative model evaluation (seasonal-naive → SARIMA/Prophet → foundation model) under temporal validation; a dispatch-cost analysis.

**Discouraged.**
- **Do not shuffle** for train/test — it is a time series; random splits leak the future.
- Do not treat the **cost metric as realized dispatch cost** — it is a declared model (`|error_MW| × hourly_CMO × 1h`), an estimate under an explicit pricing assumption, not observed cost. In hours of zero/negative CMO (physically real: spillage), modeled error cost is zero by construction.
- Do not use temperature as an *observed* same-day input — only the day-ahead forecast is leakage-safe.

**Known limitations / bias.**
- **Regime shifts** over the window: end of DST (2019), the pandemic (2020), and a temporal-grid change — three near-overlapping breaks. The DST effect on the load profile is visible but **not causally isolated** (confounded by ~7 years of trend, distributed solar growth, post-pandemic patterns).
- **Weather-station coverage:** 5 capitals stand in for a subsystem covering roughly a third of Brazil; interior/Mato Grosso conditions are underrepresented. ERA5 is reanalysis, not direct measurement.
- **Holiday calendar:** national holidays only; state/municipal holidays not encoded `[TODO: confirm scope]`.
- **CMO timezone** is inferred (empirical), not documented by ONS — a stated risk.

---

## 6. Distribution & license

Source series are public: ONS load and CMO under **CC-BY**; Open-Meteo temperature under **CC BY 4.0**. The assembled dataset is **not redistributed** as bulk files; the repository ships code plus `MANIFEST.json` (URLs + SHA-256), so anyone can reconstruct the exact snapshot via `run_all.py`. Attribution to ONS and Open-Meteo is required by their licenses.

---

## 7. Maintenance

**Maintainer / contact:** Mateus Fardin Pavan — mateusfardinpavan@gmail.com · [GitHub](https://github.com/MateusFPavan) · [LinkedIn](https://www.linkedin.com/in/mateus-fardin-pavan).
**Versioning:** the snapshot is pinned by SHA-256 in `MANIFEST.json`; `FACTS.md` is regenerated by code and is idempotent.
**Erratum policy:** because ONS revises data retrospectively, re-downloading may change historical values; any change is detectable as a hash mismatch against the manifest. Corrections would be committed with a new manifest entry `[TODO: state whether snapshots will be re-pulled on a schedule]`.

---

## Final self-check — MUST-HAVE items

All six present: **provenance/motivation** (§1, §3), **composition + data dictionary** (§2), **collection process** (§3), **preprocessing/exclusions** (§4), **uses + discouraged uses** (§5), **license** (§6).

Gaps marked inline as `[TODO]`: CMO year-by-year verification for non-2024 years, holiday-calendar scope, snapshot re-pull schedule, and confirmation of no institutional affiliation. None of these are invented; they are flagged as unestablished.
