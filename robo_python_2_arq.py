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

# 1. Pega o token configurado no GitHub
token = os.environ.get("MOTHERDUCK_TOKEN")

print("Conectando ao MotherDuck na nuvem...")
# Conecta no banco de dados 'banco_cnj' no MotherDuck
con = duckdb.connect(f"md:banco_cnj?motherduck_token={token}")

# 2. Apaga a tabela antiga para atualizar tudo do zero
print("Limpando tabela antiga...")
con.execute("DROP TABLE IF EXISTS dados_cnj_consolidado;")

primeiro_tribunal = True

print("Iniciando o download e envio dos 92 tribunais...")

# 3. Loop para baixar e salvar tribunal por tribunal
for tribunal in nome_tribunal:
    print("Processando tribunal:", tribunal)
    
    # Cria pasta temporária
    pasta_temp = "arquivos_temp"
    if not os.path.exists(pasta_temp):
        os.makedirs(pasta_temp)

    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"
    
    try:
        # Faz o download do arquivo
        resposta = requests.get(url, timeout=120)
        
        caminho_zip = f"{tribunal}.zip"
        with open(caminho_zip, "wb") as f:
            f.write(resposta.content)
            
        # Extrai os CSVs
        try:
            with zipfile.ZipFile(caminho_zip, 'r') as z:
                for nome_arquivo in z.namelist():
                    caminho_extraido = os.path.join(pasta_temp, f"{tribunal}_{nome_arquivo}")
                    with open(caminho_extraido, "wb") as f_out:
                        f_out.write(z.read(nome_arquivo))
            os.remove(caminho_zip)
        except:
            # Se vier direto como CSV
            caminho_csv = os.path.join(pasta_temp, f"{tribunal}_dados.csv")
            with open(caminho_csv, "wb") as f:
                f.write(resposta.content)
            if os.path.exists(caminho_zip):
                os.remove(caminho_zip)

        caminho_todos = os.path.join(pasta_temp, "*.csv")

        # 4. Grava direto no MotherDuck
        if primeiro_tribunal:
            con.execute(f"""
                CREATE TABLE dados_cnj_consolidado AS 
                SELECT *, '{tribunal}' AS tribunal_origem 
                FROM read_csv_auto('{caminho_todos}', union_by_name = true, ignore_errors = true);
            """)
            primeiro_tribunal = False
        else:
            con.execute(f"""
                INSERT INTO dados_cnj_consolidado 
                SELECT *, '{tribunal}' AS tribunal_origem 
                FROM read_csv_auto('{caminho_todos}', union_by_name = true, ignore_errors = true);
            """)

        print(f"Sucesso ao salvar {tribunal} no MotherDuck!")

    except Exception as erro:
        print(f"Erro no tribunal {tribunal}: {erro}")

    # 5. Apaga a pasta temporária para liberar memória do computador
    if os.path.exists(pasta_temp):
        shutil.rmtree(pasta_temp)

print("🏆 FINALIZADO! Todos os tribunais foram salvos com sucesso no MotherDuck.")
