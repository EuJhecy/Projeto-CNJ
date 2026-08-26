# Projeto-CNJ

Este projeto executa uma rotina diária automatizada para extrair e unificar as bases públicas dos 92 tribunais do Conselho Nacional de Justiça (CNJ) em um repositório.

O script roda todos os dias às 3h da manhã do horário de Brasília.

---

## O que o robô faz

1. **Coleta Automática:** Baixa diariamente os dados atualizados dos 92 tribunais brasileiros via GitHub Actions.
2. **Processamento em Streaming:** Utiliza tubos FIFO e DuckDB para ler e converter os arquivos CSV compactados em tempo real, eliminando o gargalo de espaço em disco e permitindo contornar o limite rígido de 14 GB das máquinas virtuais do GitHub.
3. **Agrupamento Otimizado:** Consolida toda a base nacional em **4 arquivos Parquet** organizados por ramo do Judiciário:
   - `1_TJs_Estaduais.parquet`
   - `2_TREs_Eleitoral.parquet`
   - `3_TRTs_Trabalho.parquet`
   - `4_TRFs_e_Superiores.parquet`

---

## Onde os dados são armazenados

Todos os arquivos Parquet consolidados são enviados automaticamente via API para o repositório público no **Hugging Face Datasets**:

**Repositório:** [`EuJhecy/dados-cnj`](https://huggingface.co/datasets/EuJhecy/dados-cnj)

---

## Por que a escolha do Hugging Face (HF)?

- O HF foi escolhido para o armazenamento porque aceita bases volumosas sem os custos e limitações de plataformas SQL em nuvem convencionais (como o Supabase e PostegreSQL).

---

## Como consultar os dados (Python + DuckDB)

```python
import duckdb

# Consulta a base inteira unificada (os 4 ramos) em uma única tabela
df = duckdb.query("""
    SELECT * 
    FROM read_parquet('hf://datasets/EuJhecy/dados-cnj/data/*.parquet', union_by_name=true)
    LIMIT 100
""").df()

print(df)****
