import os
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

# 1. Cria a pasta onde vão ficar os arquivos
pasta_arquivos = "meus_csvs"
if not os.path.exists(pasta_arquivos):
    os.makedirs(pasta_arquivos)

print("Iniciando o download dos tribunais...")

# 2. Loop para baixar arquivo por arquivo de cada tribunal
for tribunal in nome_tribunal:
    print("Baixando dados do tribunal:", tribunal)
    
    # URL da API do CNJ
    url = f"https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal={tribunal}&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"
    
    # Faz o download
    resposta = requests.get(url)
    
    # Salva o arquivo zip temporário
    caminho_zip = f"{tribunal}.zip"
    with open(caminho_zip, "wb") as f:
        f.write(resposta.content)
    
    # Tenta descompactar o arquivo zip
    try:
        with zipfile.ZipFile(caminho_zip, 'r') as z:
            # Extrai cada arquivo e adiciona o nome do tribunal no início
            for nome_arquivo in z.namelist():
                nome_novo = f"{tribunal}_{nome_arquivo}"
                caminho_extraido = os.path.join(pasta_arquivos, nome_novo)
                
                with open(caminho_extraido, "wb") as f_out:
                    f_out.write(z.read(nome_arquivo))
                    
        # Apaga o zip para não ocupar espaço
        os.remove(caminho_zip)
    except:
        # Se não for zip, salva como CSV direto
        caminho_csv = os.path.join(pasta_arquivos, f"{tribunal}_dados.csv")
        with open(caminho_csv, "wb") as f:
            f.write(resposta.content)
        if os.path.exists(caminho_zip):
            os.remove(caminho_zip)

print("Todos os downloads foram concluídos com sucesso!")

# 3. Enviar todos os CSVs para o banco de dados Supabase
print("Conectando ao banco de dados...")
url_banco = os.environ.get("URL_BANCO")

# Conecta no DuckDB
con = duckdb.connect()
con.execute("INSTALL postgres;")
con.execute("LOAD postgres;")
con.execute(f"ATTACH '{url_banco}' AS banco (TYPE POSTGRES);")

print("Juntando todos os arquivos em uma única tabela...")

# Apaga a tabela antiga se ela já existir
con.execute("DROP TABLE IF EXISTS banco.dados_cnj_consolidado;")

# Junta todos os CSVs da pasta em uma única tabela
caminho_todos_csvs = os.path.join(pasta_arquivos, "*.csv")
con.execute(f"""
    CREATE TABLE banco.dados_cnj_consolidado AS 
    SELECT *, filename AS nome_arquivo
    FROM read_csv_auto('{caminho_todos_csvs}', union_by_name = true);
""")

print("Pronto! Todos os dados foram gravados na tabela do banco.")
