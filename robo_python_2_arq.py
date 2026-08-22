import os
import shutil
import zipfile
import requests
import duckdb
from huggingface_hub import HfApi

# Lista dos 92 tribunais
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

# Configurações do Hugging Face
HF_TOKEN = os.environ.get("HF_TOKEN")
REPO_ID = "SEU_USUARIO/dados-cnj"  # Substitua pelo seu usuário e nome do dataset

api = HfApi(token=HF_TOKEN)
con = duckdb.connect()

colunas_selecionadas = """
    "Tribunal", "Grau", "Nome Orgao", "UF", "Municipio", "Ano", "Mes",
    "Processo", "Codigo da Ultima classe", "Nome da Ultima classe",
    "Codigos classes", "Codigos assuntos", "Data de referencia", "Formato",
    "id_procedimento", "Procedimento", "Recurso", "Codigo Orgao",
    "id_municipio", "Polo ativo", "Polo ativo - CNPJ",
    "Polo ativo - Natureza juridica", "Polo ativo - CNAE", "Polo passivo",
    "Polo passivo - CNPJ", "Polo passivo - Natureza juridica",
    "Polo passivo - CNAE", "Poder publico", "Materias"
"""

print("Iniciando processamento dos 92 tribunais para Parquet no Hugging Face...", flush=True)

for tribunal in nome_tribunal:
    print(f"--- Baixando e processando: {tribunal} ---", flush=True)
    
    pasta_temp = "arquivos_temp"
    os.makedirs(pasta_temp, exist_ok=True)
    
    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"
    
    try:
        resposta = requests.get(url, timeout=120)
        caminho_zip = f"{tribunal}.zip"
        with open(caminho_zip, "wb") as f:
            f.write(resposta.content)
            
        try:
            with zipfile.ZipFile(caminho_zip, 'r') as z:
                for nome_arquivo in z.namelist():
                    caminho_extraido = os.path.join(pasta_temp, f"{tribunal}_{nome_arquivo}")
                    with open(caminho_extraido, "wb") as f_out:
                        f_out.write(z.read(nome_arquivo))
            os.remove(caminho_zip)
        except:
            caminho_csv = os.path.join(pasta_temp, f"{tribunal}_dados.csv")
            with open(caminho_csv, "wb") as f:
                f.write(resposta.content)
            if os.path.exists(caminho_zip):
                os.remove(caminho_zip)

        caminho_todos_csv = os.path.join(pasta_temp, "*.csv")
        arquivo_parquet_local = f"{tribunal}.parquet"

        # Converte CSV para Parquet comprimido com ZSTD
        con.execute(f"""
            COPY (
                SELECT {colunas_selecionadas} 
                FROM read_csv_auto('{caminho_todos_csv}', union_by_name = true, ignore_errors = true)
            ) TO '{arquivo_parquet_local}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """)

        # Envia o arquivo Parquet direto para o Hugging Face
        api.upload_file(
            path_or_fileobj=arquivo_parquet_local,
            path_in_repo=f"data/{tribunal}.parquet",
            repo_id=REPO_ID,
            repo_type="dataset"
        )

        print(f"✅ {tribunal}.parquet enviado com sucesso!", flush=True)

        if os.path.exists(arquivo_parquet_local):
            os.remove(arquivo_parquet_local)

    except Exception as erro:
        print(f"❌ Erro no {tribunal}: {erro}", flush=True)

    if os.path.exists(pasta_temp):
        shutil.rmtree(pasta_temp)

print("🏆 Carga completa de todos os tribunais finalizada no Hugging Face!", flush=True)
