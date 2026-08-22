import os
import shutil
import zipfile
import requests
import duckdb
from huggingface_hub import HfApi

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

HF_TOKEN = os.environ.get("HF_TOKEN")
REPO_ID = "SEU_USUARIO/dados-cnj"  # Substitua pelo seu repositório

api = HfApi(token=HF_TOKEN)

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

con = duckdb.connect()
con.execute("SET max_memory = '5GB';")
con.execute("SET preserve_insertion_order = false;")

print("🚀 Iniciando rotina diária de atualização do Data Lake...", flush=True)

for tribunal in nome_tribunal:
    caminho_hf = f"data/{tribunal}.parquet"
    print(f"\n--- Sincronizando: {tribunal} ---", flush=True)
    
    pasta_temp = "arquivos_temp"
    os.makedirs(pasta_temp, exist_ok=True)
    
    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"
    caminho_zip = f"{tribunal}.zip"

    try:
        # Download com streaming para não estourar RAM e manter logs ativos
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            baixados = 0
            with open(caminho_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024 * 16):
                    if chunk:
                        f.write(chunk)
                        baixados += len(chunk)
                        if baixados % (1024 * 1024 * 64) == 0:  # log a cada 64MB
                            print(f"Baixando: {baixados / (1024*1024):.0f} MB...", flush=True)

        try:
            with zipfile.ZipFile(caminho_zip, 'r') as z:
                for nome_arquivo in z.namelist():
                    caminho_extraido = os.path.join(pasta_temp, f"{tribunal}_{nome_arquivo}")
                    with open(caminho_extraido, "wb") as f_out:
                        f_out.write(z.read(nome_arquivo))
            os.remove(caminho_zip)
        except Exception:
            caminho_csv = os.path.join(pasta_temp, f"{tribunal}_dados.csv")
            os.rename(caminho_zip, caminho_csv)

        caminho_todos_csv = os.path.join(pasta_temp, "*.csv")
        arquivo_parquet_local = f"{tribunal}.parquet"

        # Converte CSVs para Parquet ZSTD selecionando as 29 colunas
        con.execute(f"""
            COPY (
                SELECT {colunas_selecionadas} 
                FROM read_csv_auto('{caminho_todos_csv}', union_by_name = true, ignore_errors = true)
            ) TO '{arquivo_parquet_local}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """)

        # Sobrescreve a versão anterior no Hugging Face
        api.upload_file(
            path_or_fileobj=arquivo_parquet_local,
            path_in_repo=caminho_hf,
            repo_id=REPO_ID,
            repo_type="dataset",
            commit_message=f"Atualização diária: {tribunal}"
        )
        print(f"✅ {tribunal}.parquet atualizado no Hugging Face!", flush=True)

        if os.path.exists(arquivo_parquet_local):
            os.remove(arquivo_parquet_local)

    except Exception as erro:
        print(f"❌ Falha no tribunal {tribunal}: {erro}", flush=True)

    if os.path.exists(pasta_temp):
        shutil.rmtree(pasta_temp)

print("\n🏆 Sincronização diária finalizada!", flush=True)
