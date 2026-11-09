# 4. Off-the-shelf models, no custom fine-tuning

- **Status:** Accepted

## Context

Retrieval quality is measured against a golden baseline (`benchmarks/baselines/control.json`:
Light 100% Hit Rate / 0.917 MRR, Medium 100% Hit Rate / 0.95 MRR) and must stay
reproducible on a developer machine. Training and hosting custom models would add an
ML pipeline, a training corpus and a distribution story to a project whose job is
search over documentation. Terms in `GLOSSARY.md`: **Profile**, **TurboQuant**.

## Decision

Use off-the-shelf models only: embeddings from the **BAAI/bge** series and the
reranker from **sentence-transformers**. No custom fine-tuning.

## Consequences

- Quality work happens in retrieval plumbing — chunking, `RRF` fusion, relevance
  gates, `TurboQuant` quantization — rather than in model training.
- A profile is a configuration choice (`light`, `medium`, `full`, `full-tq`), so model
  upgrades and hardware trade-offs are config changes, not code changes.
- Ceiling on achievable quality is set by the upstream models; beating it would
  require reopening this decision.

_Provenance: migrated from the repo's earlier `CONTEXT.md` "Key Decisions"._
