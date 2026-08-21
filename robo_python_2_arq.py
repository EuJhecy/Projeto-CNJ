import os
import io
import zipfile
import requests
import duckdb

# URL do endpoint que você encontrou
URL_CNJ = "https://api-csvr.cloud.cnj.jus.br/download_csv?tribunal=CJF&indicador=&oj=&grau=&municipio=&procedimento=&codigo_ultima_classe=&codigos_assuntos=&polo_passivo=&polo_ativo=&tema=&ambiente=csv_p"

def baixar_e_extrair_dados(url, pasta_destino="./downloads"):
    os.makedirs(pasta_destino, exist_ok=True)
    
    print("🚀 Baixando dados direto da API do CNJ...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    response = requests.get(url, headers=headers, stream=True, timeout=300)
    response.raise_for_status()

    # Verifica se o arquivo retornado é um ZIP
    conteudo = response.content
    pasta_csvs = os.path.join(pasta_destino, "csvs")
    os.makedirs(pasta_csvs, exist_ok=True)

    try:
        # Tenta descompactar como ZIP
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            print("📦 Descompactando arquivos ZIP...")
            z.extractall(pasta_csvs)
            print(f"✅ Arquivos descompactados em: {pasta_csvs}")
    except zipfile.BadZipFile:
        # Se não for zip, salva como CSV único
        print("📄 Arquivo recebido é um CSV direto.")
        caminho_csv = os.path.join(pasta_csvs, "dados_cnj.csv")
        with open(caminho_csv, "wb") as f:
            f.write(conteudo)

    return pasta_csvs

def enviar_para_postgres(pasta_csvs):
    print("🐘 Conectando ao PostgreSQL (Supabase) via DuckDB...")
    
    url_banco = os.getenv("URL_BANCO")
    if not url_banco:
        raise ValueError("A variável de ambiente URL_BANCO não foi configurada.")

    if "sslmode" not in url_banco:
        url_banco += "&sslmode=require" if "?" in url_banco else "?sslmode=require"

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{url_banco}' AS meu_postgres (TYPE POSTGRES);")

    # Lista todos os CSVs baixados/extraídos
    arquivos_csv = [f for f in os.listdir(pasta_csvs) if f.endswith(".csv")]
    
    if not arquivos_csv:
        print("⚠️ Nenhum arquivo CSV encontrado na pasta.")
        return

    for arquivo in arquivos_csv:
        caminho_completo = os.path.join(pasta_csvs, arquivo)
        # Limpa o nome do arquivo para virar o nome da tabela no banco
        nome_tabela = f"cnj_{arquivo.replace('.csv', '').replace('-', '_').replace(' ', '_').lower()}"
        
        print(f"📊 Gravando '{arquivo}' na tabela 'meu_postgres.{nome_tabela}'...")
        
        # Sobrescreve a tabela com os novos dados
        con.execute(f"DROP TABLE IF EXISTS meu_postgres.{nome_tabela};")
        con.execute(f"""
            CREATE TABLE meu_postgres.{nome_tabela} AS 
            SELECT * FROM read_csv_auto('{caminho_completo}', ignore_errors=true);
        """)

    print("🏆 PROCESSO FINALIZADO! Todas as tabelas foram criadas/atualizadas com sucesso.")

if __name__ == "__main__":
    pasta_com_dados = baixar_e_extrair_dados(URL_CNJ)
    enviar_para_postgres(pasta_com_dados)
