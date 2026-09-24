# Projeto-CNJ

Este projeto executa uma rotina diária automatizada para extrair, padronizar e unificar as bases de dados públicas do Conselho Nacional de Justiça (CNJ) em um repositório otimizado.

O script roda automaticamente todos os dias às 3h da manhã (horário de Brasília) via GitHub Actions.

---
## Fonte dos Dados
Os microdados são extraídos da plataforma oficial do CNJ no painel **Estatísticas do Poder Judiciário** (aba *Download*). 
- **Endpoint da API:** Os downloads são realizados consumindo diretamente o endpoint de exportação do sistema:
  `https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={TRIBUNAL}&...`

---
## O que o robô faz

1. **Coleta Automática:** Baixa diariamente os arquivos `.zip` atualizados de todos os tribunais brasileiros.
2. **Processamento em Streaming:** Utiliza tubos FIFO (*Named Pipes*) e a engine **DuckDB** para ler e converter os arquivos CSV em tempo real, sem precisar descompactar no disco rígido. 
   > **O que isso significa na prática?** Em vez de baixar e descompactar arquivos de texto gigantescos no servidor (o que esgotaria a memória e o espaço em disco do GitHub Actions), o robô cria uma "esteira rolante virtual". O dado é lido diretamente do arquivo compactado, transformado instantaneamente na memória e salvo no formato final. Nada acumula no disco da máquina local.
   
3. **Injeção de Metadados de Rastreabilidade:** Para cada registro processado, o pipeline injeta automaticamente:
   - `dt_extracao`: Data em que a coleta foi realizada (`AAAA-MM-DD`).
   - `tabela_origem`: Nome do módulo/arquivo de origem do CNJ (ex: `CN`, `CPL`, `Sent`).
4. **Agrupamento Otimizado em Parquet:** Consolida toda a base nacional em 4 arquivos Parquet organizados por ramo do Judiciário:
   - `1_TJs_Estaduais.parquet`
   - `2_TREs_Eleitoral.parquet`
   - `3_TRTs_Trabalho.parquet`
   - `4_TRFs_e_Superiores.parquet`

---

## Onde os dados são armazenados

Todos os arquivos consolidados são salvos e organizados por mês/ano no repositório público do **Hugging Face Datasets**:

* **Repositório:** [`EuJhecy/dados-cnj`](https://huggingface.co/datasets/EuJhecy/dados-cnj)
* **Estrutura de Pastas:**
  ```text
  data/
  ├── 2026-08/
  │   ├── 1_TJs_Estaduais.parquet
  │   └── ...
  └── 2026-09/
      ├── 1_TJs_Estaduais.parquet
      ├── 2_TREs_Eleitoral.parquet
      ├── 3_TRTs_Trabalho.parquet
      └── 4_TRFs_e_Superiores.parquet
---

## Por que a escolha do Hugging Face (HF)?

1. **Escalabilidade sem custos:** O HF permite o armazenamento de bases volumosas sem os custos de plataformas SQL em nuvem convencionais (como o Supabase e PostegreSQL).

2. **Leitura direta via DuckDB:** Permite realizar consultas analíticas e filtros complexos diretamente nos arquivos remotos via HTTP, sem necessidade de baixar o dataset inteiro para a máquina local.
---

## Como consultar os dados (Python + DuckDB)

```python
import duckdb

# Consulta a base inteira unificada (os 4 ramos) em uma única tabela
df = duckdb.query("""
    SELECT * 
    FROM read_parquetread_parquet('[https://huggingface.co/datasets/EuJhecy/dados-cnj/resolve/main/data/2026-09/1_TJs_Estaduais.parquet](https://huggingface.co/datasets/EuJhecy/dados-cnj/resolve/main/data/2026-09/1_TJs_Estaduais.parquet)')
    LIMIT 100
""").df()

print(df)****
