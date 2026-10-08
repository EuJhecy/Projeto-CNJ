import glob
from datetime import datetime
import os
import requests
import subprocess
import uuid
import zipfile
import duckdb
from huggingface_hub import HfApi

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

FIFO_PIPE = "stream_dados.fifo"

print(f"🚀 Iniciando Robô CNJ - Extração e Upload para Hugging Face ({ano_mes})...\n", flush=True)

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
        url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"

        try:
            resposta = requests.get(url, stream=True, timeout=(30, 900))
            resposta.raise_for_status()

            with open(arquivo_zip, "wb") as f:
                for pedaco in resposta.iter_content(chunk_size=1024 * 1024 * 16):
                    if pedaco:
                        f.write(pedaco)

            with zipfile.ZipFile(arquivo_zip, "r") as zip_ref:
                arquivos_csv = [
                    f for f in zip_ref.namelist()
                    if f.endswith(".csv") and "tbl_correg" not in f.lower()
                ]

            for arq_csv in arquivos_csv:
                nome_apenas = os.path.basename(arq_csv)
                nome_sem_ext = os.path.splitext(nome_apenas)[0]
                tabela_origem = nome_sem_ext.split("_", 1)[-1].upper() if "_" in nome_sem_ext else nome_sem_ext.upper()

                if os.path.exists(FIFO_PIPE):
                    os.remove(FIFO_PIPE)
                os.mkfifo(FIFO_PIPE)

                proc = subprocess.Popen(f'unzip -p "{arquivo_zip}" "{arq_csv}" > "{FIFO_PIPE}"', shell=True)
                con.execute(f"CREATE OR REPLACE TEMP TABLE rascunho AS SELECT * FROM read_csv_auto('{FIFO_PIPE}', ignore_errors=true, all_varchar=true);")
                proc.wait()

                if os.path.exists(FIFO_PIPE):
                    os.remove(FIFO_PIPE)

                # Tratamento para manter apenas 1 coluna 'Tribunal'
                colunas_originais = [c[0] for c in con.execute("DESCRIBE rascunho").fetchall()]
                colunas_tribunal = [c for c in colunas_originais if c.lower() == "tribunal"]

                if len(colunas_tribunal) > 0:
                    col_trib_nome = colunas_tribunal[0]
                    sql_select = f"""
                        SELECT 
                            '{data_extracao_str}' AS dt_extracao, 
                            '{tabela_origem}' AS tabela_origem, 
                            COALESCE(NULLIF(TRIM("{col_trib_nome}"), ''), '{tribunal}') AS Tribunal, 
                            * EXCLUDE ("{col_trib_nome}") 
                        FROM rascunho
                    """
                else:
                    sql_select = f"""
                        SELECT 
                            '{data_extracao_str}' AS dt_extracao, 
                            '{tabela_origem}' AS tabela_origem, 
                            '{tribunal}' AS Tribunal, 
                            * 
                        FROM rascunho
                    """

                uid = str(uuid.uuid4())[:8]
                nome_parte = f"parte_{tribunal}_{tabela_origem}_{uid}.parquet"
                con.execute(f"COPY ({sql_select}) TO '{nome_parte}' (FORMAT PARQUET)")
                con.execute("DROP TABLE rascunho;")

            if os.path.exists(arquivo_zip):
                os.remove(arquivo_zip)

            print(f"  ✅ {tribunal} concluído!", flush=True)

        except Exception as erro:
            print(f"  ❌ Erro ao processar {tribunal}: {erro}", flush=True)

        if os.path.exists(FIFO_PIPE):
            os.remove(FIFO_PIPE)
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

print("\n🏆 PROCESSO COMPLETO FINALIZADO COM SUCESSO!")
