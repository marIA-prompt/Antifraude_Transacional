# RUNBOOK — Treinamento do motor de score antifraude

Passo a passo para rodar o treino no **VS Code** (terminal integrado) ou em outro
terminal, com **validação (critério de aceite) em cada etapa**. Comece pelo bloco de
governança — ele é pré-requisito para qualquer uso de base real.

---

## 0. Governança de dados (conta pessoal x base real)

> Enquanto o VS Code/máquina estiver logado em **e-mail pessoal**, use **somente dados
> sintéticos**. **Base real jamais em conta/ambiente pessoal.**

Riscos com dado pessoal (mesmo tokenizado) em ambiente pessoal:
- Settings Sync, OneDrive/iCloud/Drive e backups podem subir os dados para nuvem pessoal.
- Copilot/telemetria podem enviar trechos do que está aberto no editor.
- Risco de commit/push acidental para repositório pessoal.
- LGPD: dado re-identificável só pode trafegar em ambiente controlado pela empresa.

Checklist para poder usar base real (tudo verdadeiro):
- [ ] Ambiente corporativo aprovado (VM/repo da empresa, conta corporativa).
- [ ] Dado tokenizado na origem (sem CPF em claro; o gate bloqueia se houver).
- [ ] `git config user.email` = e-mail corporativo; Settings Sync/Copilot na conta certa ou desligados.
- [ ] Arquivo de dados fora do git (`.gitignore` cobre `ml/data/` e `ml/artifacts/`).
- [ ] Sync de nuvem pessoal desativado na pasta do projeto.

Enquanto qualquer item for falso: **apenas sintético**.

---

## Passo a passo (com validações)

No VS Code: `Ctrl+Shift+P` → "Python: Select Interpreter" (escolha o `.venv`) e abra o
terminal com Ctrl+`. Comandos em Linux/macOS; onde muda no Windows, está indicado.

### Passo 0 — Pré-requisitos
```bash
python3 --version
git --version
```
Validação: Python 3.10+ (testado no 3.12) e git respondem sem erro.

### Passo 1 — Obter o código
```bash
git fetch origin
git checkout cursor/ml-treinamento-modelo-1964
ls ml/
```
Validação: aparecem train.py, generate_synthetic.py, features.py, hbos.py,
data_quality.py, evaluate.py, selftest.py, config.yaml, README.md, RUNBOOK.md.

### Passo 2 — Ambiente virtual isolado
```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
```
Validação: `which python` (Windows: `where python`) aponta para dentro de `.venv`.

### Passo 3 — Instalar dependências
```bash
pip install -r ml/requirements.txt
python3 -c "import numpy, pandas, sklearn, yaml, joblib; print('deps ok')"
```
Validação: imprime `deps ok` sem ModuleNotFoundError.

### Passo 4 — Validar os contratos versionados
```bash
python3 scripts/validate_contracts.py; echo "exit=$?"
```
Validação: termina com `todos os contratos validos` e `exit=0`.

### Passo 5 — Garantias do pipeline (LGPD, leakage, gates, rótulos)
```bash
python3 -m ml.selftest
```
Validação: última linha `7 garantias verificadas`, incluindo "gate BLOQUEIA coluna de
CPF em claro" e "sem_desfecho nunca é usado como negativa".

### Passo 6 — Gerar a base sintética (LGPD-safe)
```bash
python3 -m ml.generate_synthetic --config ml/config.yaml --out ml/data
```
Validação: cria `ml/data/transactions.csv` (e `.parquet`) e imprime
`fraude_confirmada=…%` e `sem_desfecho=…%`. Confirme que NÃO há coluna `cpf` (há
`subject_token`).

### Passo 7 — Treinar (somente com sintético em conta pessoal)
```bash
python3 -m ml.train --config ml/config.yaml --data ml/data/transactions.csv --out ml/artifacts
```
Validação: bloco `--- qualidade de dados ---` todo ok; linha `split temporal:
treino=… val=… teste=…`; `calibração isotônica: global=sim cold_start=sim`; e o
`=== resumo ===` com PR-AUC, ROC-AUC, recall, precisão.

### Passo 8 — Inspecionar artefatos e métricas
Abra no VS Code:
- `ml/artifacts/report.md` — métricas gerais + por coorte.
- `ml/artifacts/metrics.json` — conjunto mínimo de promoção.
- `ml/artifacts/model_registry.json` — versões e estado `candidate`.

Validação (checklist de aceite dos ADRs):
- [ ] As 4 coortes têm métricas (sem_historico, historico_minimo, historico_parcial, historico_pleno).
- [ ] HBOS peso 0 em sem_historico/historico_minimo (ADR-0003).
- [ ] Nenhuma métrica mínima ausente.
- [ ] Split temporal respeitado (treino ≤ set, validação = out, teste = nov).

---

## Quando tiver a base real (ambiente corporativo aprovado)

Só depois do checklist de governança (seção 0) estar 100% verde.

### R1 — Formato esperado
Mesmo dicionário do `ml/README.md`: uma linha por transação, `subject_token` (nunca
CPF), timestamps em UTC, `label_category` com as 5 categorias. Parquet ou CSV.

### R2 — Colocar o arquivo fora do git
```bash
cp /caminho/corporativo/transacoes_reais.parquet ml/data/transactions_real.parquet
git status --short        # o arquivo NÃO pode aparecer aqui
```
Validação: `git status` não lista o arquivo de dados (`.gitignore` cobre `ml/data/`).

### R3 — Validar a base real ANTES de treinar (só os gates)
```bash
python3 - <<'PY'
import pandas as pd
from ml.config import load_config
from ml.data_quality import run_gates
cfg = load_config("ml/config.yaml")
df = pd.read_parquet("ml/data/transactions_real.parquet")   # ou pd.read_csv(...)
run_gates(df, cfg)
print("qualidade OK — pode treinar")
PY
```
Validação: imprime `qualidade OK — pode treinar`. Se houver CPF em claro, nulos,
duplicidade ou timestamp futuro, ele falha aqui e interrompe — corrija na origem.

### R4 — Treinar com a base real
```bash
python3 -m ml.train --config ml/config.yaml --data ml/data/transactions_real.parquet --out ml/artifacts
```
Validação: mesmos critérios do Passo 8, agora com dados reais.

---

## Conteúdo da pasta `ml/`

| Arquivo | Papel |
|---|---|
| `config.yaml` | Configuração versionada (coortes, janelas, gates) |
| `schema.py` | Colunas, coortes, categorias de rótulo, conjuntos de features |
| `generate_synthetic.py` | Gerador de dados sintéticos LGPD-safe |
| `data_quality.py` | Gates de qualidade bloqueantes |
| `features.py` | Feature engineering com segurança temporal |
| `hbos.py` | HBOS por CPF com contribuições por feature |
| `train.py` | Orquestração do treino |
| `evaluate.py` | Métricas mínimas de promoção por coorte |
| `selftest.py` | Testes de garantia |
| `README.md` | Volume/formato/estrutura dos dados |
| `RUNBOOK.md` | Este passo a passo |
| `example_transactions_sample.csv` | Amostra (500 linhas) do formato esperado |

O validador de contratos fica em `scripts/validate_contracts.py` (raiz do repositório),
com dependências em `requirements-dev.txt`.
