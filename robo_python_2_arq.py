import os
import shutil
import zipfile
import requests
import duckdb

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

# 1. Conecta ao banco de dados Supabase via DuckDB
print("Conectando ao banco de dados...")
url_banco = os.environ.get("URL_BANCO")

con = duckdb.connect()
con.execute("INSTALL postgres;")
con.execute("LOAD postgres;")
con.execute(f"ATTACH '{url_banco}' AS banco (TYPE POSTGRES);")

# Apaga a tabela antiga se já existir para começar a carga limpa
con.execute("DROP TABLE IF EXISTS banco.dados_cnj_consolidado;")

primeira_insercao = True

print("Iniciando o download e envio tribunal por tribunal...")

# 2. Loop para processar um tribunal por vez
for tribunal in nome_tribunal:
    print(f"Processando tribunal: {tribunal}...")
    
    # Cria pasta temporária para o tribunal da vez
    pasta_temp = "temp_tribunal"
    os.makedirs(pasta_temp, exist_ok=True)
    
    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"
    
    try:
        # Faz o download com timeout de segurança
        resposta = requests.get(url, timeout=180)
        
        caminho_zip = f"{tribunal}.zip"
        with open(caminho_zip, "wb") as f:
            f.write(resposta.content)
        
        # Tenta descompactar
        try:
            with zipfile.ZipFile(caminho_zip, 'r') as z:
                for nome_arq in z.namelist():
                    caminho_extraido = os.path.join(pasta_temp, f"{tribunal}_{nome_arq}")
                    with open(caminho_extraido, "wb") as f_out:
                        f_out.write(z.read(nome_arq))
            os.remove(caminho_zip)
        except:
            # Se vier direto como CSV
            with open(os.path.join(pasta_temp, f"{tribunal}_dados.csv"), "wb") as f:
                f.write(resposta.content)
            if os.path.exists(caminho_zip):
                os.remove(caminho_zip)

        # 3. Envia os arquivos deste tribunal para o banco de dados
        caminho_csvs = os.path.join(pasta_temp, "*.csv")
        
        if primeira_insercao:
            # Cria a tabela com a primeira remessa de dados
            con.execute(f"""
                CREATE TABLE banco.dados_cnj_consolidado AS 
                SELECT *, '{tribunal}' AS tribunal_origem 
                FROM read_csv_auto('{caminho_csvs}', union_by_name = true, ignore_errors = true);
            """)
            primeira_insercao = False
        else:
            # Adiciona os novos dados à tabela já existente
            con.execute(f"""
                INSERT INTO banco.dados_cnj_consolidado 
                SELECT *, '{tribunal}' AS tribunal_origem 
                FROM read_csv_auto('{caminho_csvs}', union_by_name = true, ignore_errors = true);
            """)

        print(f"✅ Dados do {tribunal} gravados com sucesso no banco!")

    except Exception as e:
        print(f"⚠️ Erro ao processar tribunal {tribunal}: {e}")

    # 4. LIMPEZA: Apaga os arquivos temporários para liberar o disco para o próximo tribunal
    if os.path.exists(pasta_temp):
        shutil.rmtree(pasta_temp)

print("🏆 Processo finalizado! Todos os tribunais foram consolidados no banco de dados.")
