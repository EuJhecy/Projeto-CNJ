import os
import shutil
import zipfile
import requests
import duckdb
from huggingface_hub import HfApi

nome_tribunal = [
    'TJSP','CJF','STJ','STM','TJAC','TJAL','TJAM','TJAP','TJBA','TJCE','TJDFT',
    'TJES','TJGO','TJMA','TJMG','TJMMG','TJMRS','TJMS','TJMSP','TJMT',
    'TJPA','TJPB','TJPE','TJPI','TJPR','TJRJ','TJRN','TJRO','TJRR','TJRS',
    'TJSC','TJSE','TJTO','TRE-AC','TRE-AL','TRE-AM','TRE-AP',
    'TRE-BA','TRE-CE','TRE-DF','TRE-ES','TRE-GO','TRE-MA','TRE-MG',
    'TRE-MS','TRE-MT','TRE-PA','TRE-PB','TRE-PE','TRE-PI','TRE-PR',
    'TRE-RJ','TRE-RN','TRE-RO','TRE-RR','TRE-RS','TRE-SC','TRE-SE',
    'TRE-SP','TRE-TO','TRF1','TRF2','TRF3','TRF4','TRF5','TRF6','TRT1',
    'TRT10','TRT11','TRT12','TRT13','TRT14','TRT15','TRT16','TRT17',
    'TRT18','TRT19','TRT2','TRT20','TRT21','TRT22','TRT23','TRT24',
    'TRT3','TRT4','TRT5','TRT6','TRT7','TRT8','TRT9','TSE','TST'
]

HF_TOKEN = os.environ.get("HF_TOKEN")
REPO_ID = "EuJhecy/dados-cnj"
ARQUIVO_BANCO_DUCK = "base_temp.duckdb"
ARQUIVO_FINAL_PARQUET = "base_cnj_completa.parquet"

api = HfApi(token=HF_TOKEN)

# Conecta ao arquivo de banco de dados temporário no disco
con = duckdb.connect(ARQUIVO_BANCO_DUCK)
con.execute("SET max_memory = '4GB';")
con.execute("SET preserve_insertion_order = false;")

print("🚀 Iniciando extração e escrita incremental em TABELA ÚNICA...", flush=True)

tabela_criada = False

for tribunal in nome_tribunal:
    print(f"\n--- Sincronizando: {tribunal} ---", flush=True)
    pasta_temp_csv = f"temp_{tribunal}"
    os.makedirs(pasta_temp_csv, exist_ok=True)
    
    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"
    caminho_zip = f"{tribunal}.zip"

    try:
        print(f"Baixando {tribunal}...", flush=True)
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(caminho_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024 * 16):
                    if chunk:
                        f.write(chunk)

        is_zip = False
        try:
            with zipfile.ZipFile(caminho_zip, 'r') as z:
                is_zip = True
                lista_arquivos = [f for f in z.namelist() if f.lower().endswith('.csv') and 'tbl_correg' not in f.lower()]
                
                for nome_arquivo in lista_arquivos:
                    nome_base = os.path.splitext(os.path.basename(nome_arquivo))[0]
                    origem = nome_base.split('_', 1)[-1].upper() if '_' in nome_base else nome_base.upper()
                    caminho_csv = z.extract(nome_arquivo, path=pasta_temp_csv)

                    # Escreve incrementalmente na tabela 'dados_unificados'
                    query_acao = "CREATE TABLE dados_unificados AS" if not tabela_criada else "INSERT INTO dados_unificados BY NAME"
                    con.execute(f"""
                        {query_acao}
                        SELECT 
                            '{tribunal}' AS tribunal,
                            '{origem}' AS tabela_origem,
                            *
                        FROM read_csv_auto('{caminho_csv}', ignore_errors = true, all_varchar = true);
                    """)
                    tabela_criada = True
                    os.remove(caminho_csv)
        except zipfile.BadZipFile:
            is_zip = False

        if not is_zip:
            caminho_csv = os.path.join(pasta_temp_csv, f"{tribunal}_dados.csv")
            os.rename(caminho_zip, caminho_csv)
            query_acao = "CREATE TABLE dados_unificados AS" if not tabela_criada else "INSERT INTO dados_unificados BY NAME"
            con.execute(f"""
                {query_acao}
                SELECT 
                    '{tribunal}' AS tribunal,
                    'DADOS_GERAIS' AS tabela_origem,
                    *
                FROM read_csv_auto('{caminho_csv}', ignore_errors = true, all_varchar = true);
            """)
            tabela_criada = True
            os.remove(caminho_csv)

    except Exception as erro:
        print(f"❌ Erro no tribunal {tribunal}: {erro}", flush=True)

    # Deleta arquivos brutos imediatamente após salvar no banco interno
    if os.path.exists(caminho_zip):
        os.remove(caminho_zip)
    if os.path.exists(pasta_temp_csv):
        shutil.rmtree(pasta_temp_csv)

# Exporta a tabela consolidada
print("\n📦 Exportando banco consolidado para arquivo Parquet único...", flush=True)
con.execute(f"""
    COPY dados_unificados TO '{ARQUIVO_FINAL_PARQUET}' (FORMAT PARQUET, COMPRESSION ZSTD);
""")
con.close()

# Deleta a base DuckDB intermediária para economizar espaço antes do upload
if os.path.exists(ARQUIVO_BANCO_DUCK):
    os.remove(ARQUIVO_BANCO_DUCK)

# Upload único do arquivo unificado
print(f"🚀 Enviando a tabela única ({ARQUIVO_FINAL_PARQUET}) para o Hugging Face...", flush=True)
api.upload_file(
    path_or_fileobj=ARQUIVO_FINAL_PARQUET,
    path_in_repo=f"data/{ARQUIVO_FINAL_PARQUET}",
    repo_id=REPO_ID,
    repo_type="dataset",
    commit_message="Base completa unificada de todos os 92 tribunais"
)

if os.path.exists(ARQUIVO_FINAL_PARQUET):
    os.remove(ARQUIVO_FINAL_PARQUET)

print("\n🏆 Dados extraídos com Sucesso!", flush=True)
