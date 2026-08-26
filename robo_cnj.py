import os
import shutil
import zipfile
import requests
import duckdb
from huggingface_hub import HfApi

# 1. LISTA COM OS 92 TRIBUNAIS DO BRASIL
nome_tribunal = [
    'CJF','STJ','STM','TJAC','TJAL','TJAM','TJAP','TJBA','TJCE','TJDFT',
    'TJES','TJGO','TJMA','TJMG','TJMMG','TJMRS','TJMS','TJMSP','TJMT',
    'TJPA','TJPB','TJPE','TJPI','TJPR','TJRJ','TJRN','TJRO','TJRR','TJRS',
    'TJSC','TJSE','TJSP','TJTO','TRE-AC','TRE-AL','TRE-AM','TRE-AP',
    'TRE-BA','TRE-CE','TRE-DF','TRE-ES','TRE-GO','TRE-MA','TRE-MG',
    'TRE-MS','TRE-MT','TRE-PA','TRE-PB','TRE-PE','TRE-PI','TRE-PR',
    'TRE-RJ','TRE-RN','TRE-RO','TRE-RR','TRE-RS','TRE-SC','TRE-SE',
    'TRE-SP','TRE-TO','TRF1','TRF2','TRF3','TRF4','TRF5','TRF6','TRT1',
    'TRT10','TRT11','TRT12','TRT13','TRT14','TRT15','TRT16','TRT17',
    'TRT18','TRT19','TRT2','TRT20','TRT21','TRT22','TRT23','TRT24',
    'TRT3','TRT4','TRT5','TRT6','TRT7','TRT8','TRT9','TSE','TST'
]

# 2. CONFIGURAÇÕES DE SENHA E ARQUIVOS
HF_TOKEN = os.environ.get("HF_TOKEN")
REPO_ID = "EuJhecy/dados-cnj"

ARQUIVO_BANCO = "base_temp.duckdb"
ARQUIVO_PARQUET_FINAL = "base_cnj_completa.parquet"

# Conecta no Hugging Face usando o Token
api = HfApi(token=HF_TOKEN)

# Se sobrou algum banco da execução passada, apaga para começar do zero
if os.path.exists(ARQUIVO_BANCO):
    os.remove(ARQUIVO_BANCO)

# Abre a conexão com o banco de dados DuckDB
con = duckdb.connect(ARQUIVO_BANCO)

# Limita o uso da memória RAM para 4 GB para não estourar o servidor
con.execute("SET max_memory = '4GB';")

print("🚀 Iniciando o robô de extração do CNJ...", flush=True)

# Variável para controlar se a tabela principal já foi criada
tabela_foi_criada = False

# 3. LOOP PRINCIPAL: PASSA TRIBUNAL POR TRIBUNAL
for tribunal in nome_tribunal:
    print(f"\n----------------------------------------", flush=True)
    print(f"Processando tribunal: {tribunal}", flush=True)
    print(f"----------------------------------------", flush=True)

    # Nomes das pastas e arquivos temporários deste tribunal
    pasta_temp = f"pasta_{tribunal}"
    arquivo_zip = f"{tribunal}.zip"
    os.makedirs(pasta_temp, exist_ok=True)

    # URL oficial de download do CNJ
    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"

    try:
        # PASSO A: Baixar o arquivo ZIP do tribunal
        print(f"1. Baixando arquivo {arquivo_zip}...", flush=True)
        resposta = requests.get(url, stream=True, timeout=(30, 900))
        resposta.raise_for_status()

        with open(arquivo_zip, "wb") as f:
            for pedaco in resposta.iter_content(chunk_size=1024 * 1024 * 16):
                if pedaco:
                    f.write(pedaco)

        # PASSO B: Extrair os arquivos CSV do ZIP
        print("2. Extraindo arquivos CSV...", flush=True)
        with zipfile.ZipFile(arquivo_zip, 'r') as zip_ref:
            zip_ref.extractall(pasta_temp)

        # Pega a lista de todos os CSVs extraídos (ignorando tabelas da corregedoria)
        arquivos_csv = [f for f in os.listdir(pasta_temp) if f.endswith('.csv') and 'tbl_correg' not in f.lower()]

       # PASSO C: Ler cada CSV e salvar no banco DuckDB
        for arquivo in arquivos_csv:
            caminho_csv = os.path.join(pasta_temp, arquivo)

            # Descobre o nome da tabela de origem (ex: CN, CPL, CTC)
            nome_sem_ext = os.path.splitext(arquivo)[0]
            if '_' in nome_sem_ext:
                tabela_origem = nome_sem_ext.split('_', 1)[-1].upper()
            else:
                tabela_origem = nome_sem_ext.upper()

            # Lê o CSV para uma tabela temporária de rascunho
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE rascunho AS 
                SELECT * FROM read_csv_auto('{caminho_csv}', ignore_errors=true, all_varchar=true);
            """)

            # Pega a lista de colunas exatamente como vieram do CSV (respeitando maiúsculas)
            colunas_originais = [coluna[0] for coluna in con.execute("DESCRIBE rascunho").fetchall()]

            # Procura qual é o nome exato da coluna tribunal (Tribunal, TRIBUNAL, tribunal...)
            nome_exato_tribunal = None
            for coluna in colunas_originais:
                if coluna.lower() == 'tribunal':
                    nome_exato_tribunal = coluna
                    break

            # Se encontrou a coluna no arquivo original, a gente exclui ela pelo NOME EXATO usando aspas duplas.
            # Em seguida, criamos a nossa coluna padronizada chamada 'Tribunal'
            if nome_exato_tribunal:
                sql_select = f"SELECT '{tabela_origem}' AS tabela_origem, '{tribunal}' AS Tribunal, * EXCLUDE (\"{nome_exato_tribunal}\") FROM rascunho"
            else:
                sql_select = f"SELECT '{tabela_origem}' AS tabela_origem, '{tribunal}' AS Tribunal, * FROM rascunho"

            # Se a tabela principal 'dados_unificados' ainda NÃO existe, cria ela
            if not tabela_foi_criada:
                con.execute(f"CREATE TABLE dados_unificados AS {sql_select};")
                tabela_foi_criada = True
            # Se já existe, apenas cola as novas linhas
            else:
                con.execute(f"INSERT INTO dados_unificados BY NAME {sql_select};")

            # Apaga o rascunho e remove o arquivo CSV lido
            con.execute("DROP TABLE rascunho;")
            os.remove(caminho_csv)

        print(f"✅ Tribunal {tribunal} processado com sucesso!", flush=True)

    except Exception as erro:
        print(f"❌ Erro ao processar o tribunal {tribunal}: {erro}", flush=True)

    # PASSO D: Limpeza de segurança após terminar o tribunal
    if os.path.exists(arquivo_zip):
        os.remove(arquivo_zip)
    if os.path.exists(pasta_temp):
        shutil.rmtree(pasta_temp)

# 4. EXPORTAR A TABELA COMPLETA PARA UM ARQUIVO PARQUET ÚNICO
print("\n📦 Salvando a base unificada em arquivo Parquet...", flush=True)
con.execute(f"""
    COPY dados_unificados TO '{ARQUIVO_PARQUET_FINAL}' (FORMAT PARQUET, COMPRESSION ZSTD);
""")

# Fecha a conexão com o banco e apaga o arquivo temporário do DuckDB
con.close()
if os.path.exists(ARQUIVO_BANCO):
    os.remove(ARQUIVO_BANCO)

# 5. ENVIAR O ARQUIVO PARQUET FINAL PARA O HUGGING FACE
print(f"🚀 Enviando {ARQUIVO_PARQUET_FINAL} para o Hugging Face...", flush=True)
api.upload_file(
    path_or_fileobj=ARQUIVO_PARQUET_FINAL,
    path_in_repo=f"data/{ARQUIVO_PARQUET_FINAL}",
    repo_id=REPO_ID,
    repo_type="dataset",
    commit_message="Atualização da base gigante unificada de todos os 92 tribunais"
)

# Limpa o arquivo Parquet local final
if os.path.exists(ARQUIVO_PARQUET_FINAL):
    os.remove(ARQUIVO_PARQUET_FINAL)

print("\n🏆 Processo finalizado com sucesso!", flush=True)
