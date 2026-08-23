import os
import glob
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
REPO_ID = "EuJhecy/dados-cnj" 

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
    print(f"\n==========================================", flush=True)
    print(f"--- Sincronizando: {tribunal} ---", flush=True)
    print(f"==========================================", flush=True)
    
    pasta_temp_csv = "temp_csv"
    pasta_temp_parquet = "temp_parquet_partes"
    os.makedirs(pasta_temp_csv, exist_ok=True)
    os.makedirs(pasta_temp_parquet, exist_ok=True)
    
    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"
    caminho_zip = f"{tribunal}.zip"
    arquivo_parquet_local = f"{tribunal}.parquet"

    try:
        # 1. Download em streaming com log periódico
        print(f"Baixando {tribunal}...", flush=True)
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            baixados = 0
            with open(caminho_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024 * 16):
                    if chunk:
                        f.write(chunk)
                        baixados += len(chunk)
                        if baixados % (1024 * 1024 * 64) == 0:
                            print(f"Baixando: {baixados / (1024*1024):.0f} MB...", flush=True)

        # 2. Processamento 1 a 1: Extrai CSV -> Converte Parquet -> Apaga CSV
        is_zip = False
        try:
            with zipfile.ZipFile(caminho_zip, 'r') as z:
                is_zip = True
                lista_arquivos = [f for f in z.namelist() if f.lower().endswith('.csv')]
                total = len(lista_arquivos)
                print(f"📦 Extraindo e convertendo {total} arquivos internamente...", flush=True)

                for idx, nome_arquivo in enumerate(lista_arquivos, start=1):
                    # Extrai apenas ESTE arquivo CSV
                    caminho_csv = z.extract(nome_arquivo, path=pasta_temp_csv)
                    caminho_parquet_parte = os.path.join(pasta_temp_parquet, f"parte_{idx}.parquet")

                    # Converte este CSV isolado para Parquet
                    con.execute(f"""
                        COPY (
                            SELECT {colunas_selecionadas} 
                            FROM read_csv_auto('{caminho_csv}', union_by_name = true, ignore_errors = true)
                        ) TO '{caminho_parquet_parte}' (FORMAT PARQUET, COMPRESSION ZSTD);
                    """)

                    # APAGA o CSV imediatamente para liberar o disco
                    if os.path.exists(caminho_csv):
                        os.remove(caminho_csv)
                    print(f"  -> Concluído [{idx}/{total}]: {nome_arquivo} convertido e CSV apagado.", flush=True)
        except zipfile.BadZipFile:
            # Caso a API tenha devolvido um CSV direto em vez de ZIP
            is_zip = False

        if not is_zip:
            caminho_csv = os.path.join(pasta_temp_csv, f"{tribunal}_dados.csv")
            os.rename(caminho_zip, caminho_csv)
            caminho_parquet_parte = os.path.join(pasta_temp_parquet, "parte_1.parquet")
            con.execute(f"""
                COPY (
                    SELECT {colunas_selecionadas} 
                    FROM read_csv_auto('{caminho_csv}', union_by_name = true, ignore_errors = true)
                ) TO '{caminho_parquet_parte}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """)
            if os.path.exists(caminho_csv):
                os.remove(caminho_csv)

        # Remove o arquivo ZIP baixado antes de consolidar
        if os.path.exists(caminho_zip):
            os.remove(caminho_zip)

        # 3. Une as partes Parquet leves em um único tribunal.parquet
        print(f"🔄 Consolidando partes em {arquivo_parquet_local}...", flush=True)
        con.execute(f"""
            COPY (
                SELECT * FROM read_parquet('{pasta_temp_parquet}/*.parquet')
            ) TO '{arquivo_parquet_local}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """)

        # 4. Upload para o Hugging Face
        print(f"Subindo {arquivo_parquet_local} para o Hugging Face...", flush=True)
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

    # Limpeza de pastas temporárias
    if os.path.exists(pasta_temp_csv):
        shutil.rmtree(pasta_temp_csv)
    if os.path.exists(pasta_temp_parquet):
        shutil.rmtree(pasta_temp_parquet)
    if os.path.exists(caminho_zip):
        os.remove(caminho_zip)

print("\n🏆 Sincronização diária finalizada!", flush=True)
