# JobPilot

Agente autonomo de candidaturas. Ingere vagas, avalia o *fit* com o meu CV,
gera CV e carta de apresentacao adaptados para cada vaga e monta uma **fila de
candidaturas prontas** para envio.

**Decisao de produto:** o agente e autonomo ate a fila. O **envio final e
sempre um clique humano** — nunca submit automatico em job board de terceiro.
Motivo: (1) ToS de LinkedIn/Gupy e afins proibem automacao de submit; (2)
candidatar para a vaga errada e o classico *fail-open* (o gate que aprova
quando devia barrar). O ponto de decisao fica com a pessoa.

## Arquitetura (portas e adapters)

```
[JobSource] -> [Normalizer] -> [Matcher] -> [Generator] -> [ApplicationQueue] -> [Report/UI]
  (porta)      (Job canonico)  (score+fit)  (CV+carta)     (persistencia)        (1 clique)
```

A fonte de vaga e plugavel: o nucleo nao depende de *de onde vem a vaga*.

## Stack

- Python 3.12+ / FastAPI
- pytest + pytest-cov com **gate de cobertura** (`--cov-fail-under=80`)
- SQLite (persistencia local, a partir do M1)

## Rodando

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# bash/macOS/Linux:    source .venv/bin/activate
pip install -e ".[dev]"

# API
uvicorn jobpilot.app:app --reload
# health: http://127.0.0.1:8000/health

# Testes + cobertura
pytest
```

## Estado

M0 (esqueleto) concluido: FastAPI + health check + gate de cobertura ativo e
verificado no caminho de reprovacao. Milestones seguintes (M1+) sao entregues
por spec-driven development.

## Roadmap

Ver o briefing de planejamento para o detalhe dos milestones M0–M7.
