import glob
import io
import os
from datetime import datetime
import shutil
import uuid
import zipfile
import duckdb
from huggingface_hub import HfApi
import requests

# Configuração de data
data_atual = datetime.now()
ano_mes = data_atual.strftime("%Y-%m")
data_extracao_str = data_atual.strftime("%Y-%m-%d")

# Mapeamento completo dos 92 tribunais divididos por ramos
ramos_judiciario = {
    "1_TJs_Estaduais": [
        'TJAC', 'TJAL', 'TJAM', 'TJAP', 'TJBA', 'TJCE', 'TJDFT', 'TJES', 'TJGO', 'TJMA',
        'TJMG', 'TJMMG', 'TJMRS', 'TJMS', 'TJMSP', 'TJMT', 'TJPA', 'TJPB', 'TJPE', 'TJPI',
        'TJPR', 'TJRJ', 'TJRN', 'TJRO', 'TJRR', 'TJRS', 'TJSC', 'TJSE', 'TJSP', 'TJTO'
    ],
    "2_TREs_Eleitoral": [
        'TRE-AC', 'TRE-AL', 'TRE-AM', 'TRE-AP', 'TRE-BA', 'TRE-CE', 'TRE-DF', 'TRE-ES', 'TRE-GO', 'TRE-MA',
        'TRE-MG', 'TRE-MS', 'TRE-MT', 'TRE-PA', 'TRE-PB', 'TRE-PE', 'TRE-PI', 'TRE-PR', 'TRE-RJ', 'TRE-RN',
        'TRE-RO', 'TRE-RR', 'TRE-RS', 'TRE-SC', 'TRE-SE', 'TRE-SP', 'TRE-TO'
    ],
    "3_TRTs_Trabalho": [
        'TRT1', 'TRT2', 'TRT3', 'TRT4', 'TRT5', 'TRT6', 'TRT7', 'TRT8', 'TRT9', 'TRT10',
        'TRT11', 'TRT12', 'TRT13', 'TRT14', 'TRT15', 'TRT16', 'TRT17', 'TRT18', 'TRT19', 'TRT20',
        'TRT21', 'TRT22', 'TRT23', 'TRT24'
    ],
    "4_TRFs_e_Superiores": [
        'TRF1', 'TRF2', 'TRF3', 'TRF4', 'TRF5', 'TRF6', 'CJF', 'STJ', 'STM', 'TSE', 'TST'
    ]
}

HF_TOKEN = os.environ.get("HF_TOKEN")
REPO_ID = "EuJhecy/dados-cnj"

if not HF_TOKEN:
    raise ValueError("❌ Erro fatal: A variável de ambiente HF_TOKEN não foi configurada nos Secrets do GitHub!")

api = HfApi(token=HF_TOKEN)
con = duckdb.connect()
con.execute("SET max_memory = '6GB';")

TEMP_CSV = "temp_stream.csv"

def processar_csv_duckdb(caminho_csv_local, tabela_origem, tribunal_nome):
    """Lê o CSV local via DuckDB, ajusta metadados e salva como parquet local."""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE rascunho AS 
        SELECT * FROM read_csv_auto('{caminho_csv_local}', ignore_errors=true, all_varchar=true);
    """)

    # Tratamento para manter apenas 1 coluna 'Tribunal'
    colunas_originais = [c[0] for c in con.execute("DESCRIBE rascunho").fetchall()]
    colunas_tribunal = [c for c in colunas_originais if c.lower() == "tribunal"]

    if len(colunas_tribunal) > 0:
        col_trib_nome = colunas_tribunal[0]
        sql_select = f"""
            SELECT 
                '{data_extracao_str}' AS dt_extracao, 
                '{tabela_origem}' AS tabela_origem, 
                COALESCE(NULLIF(TRIM("{col_trib_nome}"), ''), '{tribunal_nome}') AS Tribunal, 
                * EXCLUDE ("{col_trib_nome}") 
            FROM rascunho
        """
    else:
        sql_select = f"""
            SELECT 
                '{data_extracao_str}' AS dt_extracao, 
                '{tabela_origem}' AS tabela_origem, 
                '{tribunal_nome}' AS Tribunal, 
                * 
            FROM rascunho
        """

    uid = str(uuid.uuid4())[:8]
    nome_parte = f"parte_{tribunal_nome}_{tabela_origem}_{uid}.parquet"
    con.execute(f"COPY ({sql_select}) TO '{nome_parte}' (FORMAT PARQUET)")
    con.execute("DROP TABLE rascunho;")


def Mapear_tabela_origem(nome_arquivo):
    """Identifica com precisão a sigla da tabela de origem."""
    caminho_upper = nome_arquivo.upper()
    if "CN" in caminho_upper and "CP" not in caminho_upper:
        return "CN"
    elif "SENT" in caminho_upper:
        return "SENT"
    elif "TBAIX" in caminho_upper:
        return "TBAIX"
    elif "CPMAIS15ANOS" in caminho_upper or "15ANOS" in caminho_upper:
        return "CPMAIS15ANOS"
    elif "CP" in caminho_upper or "CPL" in caminho_upper:
        return "CP"
    else:
        nome_apenas = os.path.basename(nome_arquivo)
        nome_sem_ext = os.path.splitext(nome_apenas)[0]
        return nome_sem_ext.split("_")[-1].upper()


print(f" Iniciando Robô CNJ - Extração e Upload para Hugging Face ({ano_mes})...\n", flush=True)

for nome_ramo, lista_tribunais in ramos_judiciario.items():
    print(f"========================================", flush=True)
    print(f"PROCESSANDO RAMO: {nome_ramo} ({len(lista_tribunais)} tribunais)", flush=True)
    print(f"========================================", flush=True)

    # Limpa partes de execuções ou ramos anteriores
    for f in glob.glob("parte_*.parquet"):
        os.remove(f)

    for tribunal in lista_tribunais:
        print(f"--- Extraindo: {tribunal} ---", flush=True)
        arquivo_zip = f"{tribunal}.zip"
        
        # URL do ClickHouse
        url = f"https://api-estatisticas-clickhouse.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&id_orgao_julgador=&grau=&municipio_oj=&procedimento=&id_ultima_classe=&id_assunto=&polo_passivo=&polo_ativo=&tema=&extensao=csv"

        try:
            resposta = requests.get(url, stream=True, timeout=(30, 900))
            resposta.raise_for_status()

            with open(arquivo_zip, "wb") as f:
                for pedaco in resposta.iter_content(chunk_size=1024 * 1024 * 16):
                    if pedaco:
                        f.write(pedaco)

            # Lendo o ZIP principal e descompactando os SUB-ZIPs na memória
            with zipfile.ZipFile(arquivo_zip, "r") as main_zip:
                for item in main_zip.infolist():
                    tabela_origem = Mapear_tabela_origem(item.filename)

                    # Caso 1: Arquivo é um sub-ZIP (ex: TJDFT_CN.zip)
                    if item.filename.lower().endswith(".zip"):
                        bytes_sub_zip = main_zip.read(item.filename)
                        with zipfile.ZipFile(io.BytesIO(bytes_sub_zip)) as sub_zip:
                            for arq_csv in sub_zip.namelist():
                                if arq_csv.lower().endswith(".csv") and "tbl_correg" not in arq_csv.lower():
                                    with sub_zip.open(arq_csv) as source, open(TEMP_CSV, "wb") as target:
                                        shutil.copyfileobj(source, target)
                                    
                                    processar_csv_duckdb(TEMP_CSV, tabela_origem, tribunal)
                                    
                                    if os.path.exists(TEMP_CSV):
                                        os.remove(TEMP_CSV)

                    # Caso 2: Arquivo é um CSV direto no pacote principal
                    elif item.filename.lower().endswith(".csv") and "tbl_correg" not in item.filename.lower():
                        with main_zip.open(item.filename) as source, open(TEMP_CSV, "wb") as target:
                            shutil.copyfileobj(source, target)
                        
                        processar_csv_duckdb(TEMP_CSV, tabela_origem, tribunal)
                        
                        if os.path.exists(TEMP_CSV):
                            os.remove(TEMP_CSV)

            if os.path.exists(arquivo_zip):
                os.remove(arquivo_zip)

            print(f"   ✅ {tribunal} concluído!", flush=True)

        except Exception as erro:
            print(f"   ❌ Erro ao processar {tribunal}: {erro}", flush=True)

        if os.path.exists(TEMP_CSV):
            os.remove(TEMP_CSV)
        if os.path.exists(arquivo_zip):
            os.remove(arquivo_zip)

    # UNIFICAÇÃO E UPLOAD DO RAMO
    arquivo_ramo_local = f"{nome_ramo}_{ano_mes}.parquet"
    caminho_hf = f"data/{ano_mes}/{nome_ramo}.parquet"

    print(f"\n Subindo ramo {nome_ramo} para o Hugging Face...", flush=True)

    try:
        con.execute(f"""
            COPY (
                SELECT * FROM read_parquet('parte_*.parquet', union_by_name=true)
            ) TO '{arquivo_ramo_local}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """)

        api.upload_file(
            path_or_fileobj=arquivo_ramo_local,
            path_in_repo=caminho_hf,
            repo_id=REPO_ID,
            repo_type="dataset",
            commit_message=f"Atualização da base {nome_ramo} ({ano_mes})"
        )
        print(f" Ramo {nome_ramo} enviado com sucesso!", flush=True)

    except Exception as erro:
        print(f"❌ Erro no upload do ramo {nome_ramo}: {erro}", flush=True)

    # Limpeza do disco antes de passar pro próximo ramo
    if os.path.exists(arquivo_ramo_local):
        os.remove(arquivo_ramo_local)
    for f in glob.glob("parte_*.parquet"):
        os.remove(f)

print("\n PROCESSO COMPLETO FINALIZADO COM SUCESSO!")
