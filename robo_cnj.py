import os
import shutil
import zipfile
import glob
import subprocess
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

# 2. CONFIGURAÇÕES DA API E DUCKDB
HF_TOKEN = os.environ.get("HF_TOKEN")
REPO_ID = "EuJhecy/dados-cnj"

api = HfApi(token=HF_TOKEN)
con = duckdb.connect()
con.execute("SET max_memory = '4GB';")

FIFO_PIPE = "stream_dados.fifo"

print("🚀 Processando e enviando tribunal por tribunal (92 arquivos no total)...", flush=True)

# 3. LOOP PRINCIPAL
for tribunal in nome_tribunal:
    print(f"\n----------------------------------------", flush=True)
    print(f"Processando tribunal: {tribunal}", flush=True)
    print(f"----------------------------------------", flush=True)

    arquivo_zip = f"{tribunal}.zip"
    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"

    try:
        # PASSO A: Baixar arquivo ZIP do tribunal
        resposta = requests.get(url, stream=True, timeout=(30, 900))
        resposta.raise_for_status()

        with open(arquivo_zip, "wb") as f:
            for pedaco in resposta.iter_content(chunk_size=1024 * 1024 * 16):
                if pedaco:
                    f.write(pedaco)

        # PASSO B: Mapear CSVs dentro do ZIP
        with zipfile.ZipFile(arquivo_zip, 'r') as zip_ref:
            arquivos_csv = [f for f in zip_ref.namelist() if f.endswith('.csv') and 'tbl_correg' not in f.lower()]

        # PASSO C: Processar cada CSV em tempo real via Pipe FIFO (Sem salvar CSV no disco)
        for arq_csv in arquivos_csv:
            nome_apenas = os.path.basename(arq_csv)
            nome_sem_ext = os.path.splitext(nome_apenas)[0]
            tabela_origem = nome_sem_ext.split('_', 1)[-1].upper() if '_' in nome_sem_ext else nome_sem_ext.upper()

            if os.path.exists(FIFO_PIPE):
                os.remove(FIFO_PIPE)
            os.mkfifo(FIFO_PIPE)

            proc = subprocess.Popen(f'unzip -p "{arquivo_zip}" "{arq_csv}" > "{FIFO_PIPE}"', shell=True)
            con.execute(f"CREATE OR REPLACE TEMP TABLE rascunho AS SELECT * FROM read_csv_auto('{FIFO_PIPE}', ignore_errors=true, all_varchar=true);")
            proc.wait()

            if os.path.exists(FIFO_PIPE):
                os.remove(FIFO_PIPE)

            colunas_originais = [c[0] for c in con.execute("DESCRIBE rascunho").fetchall()]
            colunas_tribunal = [c for c in colunas_originais if c.lower() == 'tribunal']

            if len(colunas_tribunal) > 0:
                texto_excluir = ", ".join([f'"{c}"' for c in colunas_tribunal])
                sql_select = f"SELECT '{tabela_origem}' AS tabela_origem, '{tribunal}' AS Tribunal, * EXCLUDE ({texto_excluir}) FROM rascunho"
            else:
                sql_select = f"SELECT '{tabela_origem}' AS tabela_origem, '{tribunal}' AS Tribunal, * FROM rascunho"

            nome_parte = f"parte_{tribunal}_{tabela_origem}.parquet"
            con.execute(f"COPY ({sql_select}) TO '{nome_parte}' (FORMAT PARQUET)")
            con.execute("DROP TABLE rascunho;")

        # PASSO D: Limpar ZIP antes da unificação
        if os.path.exists(arquivo_zip):
            os.remove(arquivo_zip)

        # PASSO E: Unificar as tabelas do tribunal e enviar para o Hugging Face
        nome_arquivo_tribunal = f"{tribunal}.parquet"
        con.execute(f"""
            COPY (
                SELECT * FROM read_parquet('parte_{tribunal}_*.parquet', union_by_name=true)
            ) TO '{nome_arquivo_tribunal}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """)

        api.upload_file(
            path_or_fileobj=nome_arquivo_tribunal,
            path_in_repo=f"data/{nome_arquivo_tribunal}",
            repo_id=REPO_ID,
            repo_type="dataset",
            commit_message=f"Adicionando base processada do tribunal {tribunal}"
        )

        # PASSO F: Faxina dos arquivos do tribunal localmente
        os.remove(nome_arquivo_tribunal)
        for f in glob.glob(f"parte_{tribunal}_*.parquet"):
            os.remove(f)

        print(f"✅ Tribunal {tribunal} enviado e limpo com sucesso!", flush=True)

    except Exception as erro:
        print(f"❌ Erro ao processar {tribunal}: {erro}", flush=True)

    if os.path.exists(FIFO_PIPE):
        os.remove(FIFO_PIPE)
    if os.path.exists(arquivo_zip):
        os.remove(arquivo_zip)

print("\n🏆 Processo finalizado com sucesso!", flush=True)
