import os
import shutil
import zipfile
import glob
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

# 2. CONFIGURAÇÕES
HF_TOKEN = os.environ.get("HF_TOKEN")
REPO_ID = "EuJhecy/dados-cnj"
ARQUIVO_PARQUET_FINAL = "base_cnj_completa.parquet"

api = HfApi(token=HF_TOKEN)
con = duckdb.connect()
con.execute("SET max_memory = '4GB';")

print("🚀 Iniciando o robô de extração em blocos (Mini-Parquets)...", flush=True)

# Limpeza de segurança de execuções anteriores
for f in glob.glob("parte_*.parquet"):
    os.remove(f)

# 3. LOOP PRINCIPAL
for tribunal in nome_tribunal:
    print(f"\n----------------------------------------", flush=True)
    print(f"Processando tribunal: {tribunal}", flush=True)
    print(f"----------------------------------------", flush=True)

    pasta_temp = f"pasta_{tribunal}"
    arquivo_zip = f"{tribunal}.zip"
    os.makedirs(pasta_temp, exist_ok=True)

    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"

    try:
        # PASSO A: Baixar ZIP
        print(f"1. Baixando arquivo ZIP...", flush=True)
        resposta = requests.get(url, stream=True, timeout=(30, 900))
        resposta.raise_for_status()

        with open(arquivo_zip, "wb") as f:
            for pedaco in resposta.iter_content(chunk_size=1024 * 1024 * 16):
                if pedaco:
                    f.write(pedaco)

        # PASSO B: Extrair CSVs
        print("2. Extraindo arquivos CSV...", flush=True)
        with zipfile.ZipFile(arquivo_zip, 'r') as zip_ref:
            zip_ref.extractall(pasta_temp)

        arquivos_csv = [f for f in os.listdir(pasta_temp) if f.endswith('.csv') and 'tbl_correg' not in f.lower()]

        # PASSO C: Criar os Mini-Parquets
        for arquivo in arquivos_csv:
            caminho_csv = os.path.join(pasta_temp, arquivo)

            nome_sem_ext = os.path.splitext(arquivo)[0]
            if '_' in nome_sem_ext:
                tabela_origem = nome_sem_ext.split('_', 1)[-1].upper()
            else:
                tabela_origem = nome_sem_ext.upper()

            con.execute(f"CREATE OR REPLACE TEMP TABLE rascunho AS SELECT * FROM read_csv_auto('{caminho_csv}', ignore_errors=true, all_varchar=true);")

            # Pega TODAS as colunas originais do CSV
            colunas_originais = [c[0] for c in con.execute("DESCRIBE rascunho").fetchall()]

            # Encontra TODAS as colunas que se chamam 'tribunal' (com maiúscula, minúscula, etc)
            colunas_tribunal = [c for c in colunas_originais if c.lower() == 'tribunal']

            # Se encontrar, exclui todas de uma vez para não sobrar duplicata
            if len(colunas_tribunal) > 0:
                texto_excluir = ", ".join([f'"{c}"' for c in colunas_tribunal])
                sql_select = f"SELECT '{tabela_origem}' AS tabela_origem, '{tribunal}' AS Tribunal, * EXCLUDE ({texto_excluir}) FROM rascunho"
            else:
                sql_select = f"SELECT '{tabela_origem}' AS tabela_origem, '{tribunal}' AS Tribunal, * FROM rascunho"

            # Nome do mini arquivo (Ex: parte_TJSP_CN.parquet)
            nome_parte = f"parte_{tribunal}_{tabela_origem}.parquet"
            
            # Copia direto do SQL para o arquivo no disco (já nasce compactado)
            con.execute(f"COPY ({sql_select}) TO '{nome_parte}' (FORMAT PARQUET)")
            
            con.execute("DROP TABLE rascunho;")
            os.remove(caminho_csv)

        print(f"✅ Tribunal {tribunal} processado com sucesso!", flush=True)

    except Exception as erro:
        print(f"❌ Erro ao processar o tribunal {tribunal}: {erro}", flush=True)

    # PASSO D: Limpeza do tribunal
    if os.path.exists(arquivo_zip):
        os.remove(arquivo_zip)
    if os.path.exists(pasta_temp):
        shutil.rmtree(pasta_temp)


# 4. juntando tudo
print("\n📦 Juntando todos os arquivos em um único Parquet...", flush=True)
# O "union_by_name=true" aceita que os tribunais tenham colunas diferentes sem dar erro!
con.execute(f"""
    COPY (
        SELECT * FROM read_parquet('parte_*.parquet', union_by_name=true)
    ) TO '{ARQUIVO_PARQUET_FINAL}' (FORMAT PARQUET, COMPRESSION ZSTD);
""")

con.close()

# Apagar os pedaços soltos para limpar o servidor
for f in glob.glob("parte_*.parquet"):
    os.remove(f)

# 5. UPLOAD PARA O HUGGING FACE
print(f"🚀 Enviando a base unificada para o Hugging Face...", flush=True)
api.upload_file(
    path_or_fileobj=ARQUIVO_PARQUET_FINAL,
    path_in_repo=f"data/{ARQUIVO_PARQUET_FINAL}",
    repo_id=REPO_ID,
    repo_type="dataset",
    commit_message="Base CNJ unificada com suporte a colunas variáveis (schema evolution)"
)

if os.path.exists(ARQUIVO_PARQUET_FINAL):
    os.remove(ARQUIVO_PARQUET_FINAL)

print("\n🏆 Processo finalizado com sucesso!", flush=True)
