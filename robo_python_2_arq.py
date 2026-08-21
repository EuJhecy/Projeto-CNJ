import os
import re
import csv
import zipfile
import io
import duckdb
from datetime import datetime
from playwright.sync_api import sync_playwright

arquivos_baixados = {}

def espiar_resposta(response):
    url = response.url.lower()
    headers = response.headers
    content_type = headers.get("content-type", "").lower()
    
    # Intercepta arquivos ZIP ou CSV vindos da API
    if ".zip" in url or "application/zip" in content_type or "application/x-zip-compressed" in content_type:
        try:
            if response.status == 200:
                print(f"⚡ Arquivo ZIP capturado direto da rede!")
                arquivos_baixados["pacote.zip"] = response.body()
        except Exception as e:
            print(f"Erro ao capturar ZIP: {e}")

    elif ".csv" in url or "text/csv" in content_type:
        try:
            if response.status == 200:
                nome = url.split("/")[-1].split("?")[0]
                if not nome.endswith(".csv"):
                    nome = f"tabela_{len(arquivos_baixados)}.csv"
                print(f"⚡ Tabela CSV capturada direto da rede: {nome}")
                arquivos_baixados[nome] = response.text()
        except Exception as e:
            print(f"Erro ao capturar CSV: {e}")

def rodar_automacao():
    print("🚀 Iniciando captura direta de dados pela rede...")
    
    pasta_download = os.path.abspath("./downloads")
    os.makedirs(pasta_download, exist_ok=True)
    caminho_csv_final = os.path.join(pasta_download, "dados_cnj_unificados.csv")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="pt-BR"
        )
        page = context.new_page()
        page.on("response", espiar_resposta)

        print("🌐 Acessando o painel do CNJ para carregar os dados...")
        page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/", wait_until="domcontentloaded", timeout=90000)
        
        # Aguarda as requisições de fundo terminarem de trafegar
        print("⏳ Aguardando os dados trafegarem pela rede (50s)...")
        page.wait_for_timeout(50000)

        browser.close()

    if not arquivos_baixados:
        raise Exception("Nenhum dado (ZIP ou CSV) foi capturado da rede.")

    cabecalho = None
    todas_as_linhas = []

    # Se capturou o pacote ZIP completo
    if "pacote.zip" in arquivos_baixados:
        print("📂 Processando pacote ZIP capturado da rede...")
        with zipfile.ZipFile(io.BytesIO(arquivos_baixados["pacote.zip"])) as zip_ref:
            for nome_arquivo in zip_ref.namelist():
                if nome_arquivo.endswith('.csv'):
                    with zip_ref.open(nome_arquivo) as f:
                        conteudo = f.read().decode('utf-8-sig', errors='ignore').splitlines()
                        leitor = csv.reader(conteudo, delimiter=';')
                        linhas = list(leitor)
                        if linhas:
                            if cabecalho is None:
                                cabecalho = linhas[0] + ["origem_tabela"]
                            nome_origem = os.path.splitext(os.path.basename(nome_arquivo))[0]
                            for linha in linhas[1:]:
                                if linha:
                                    todas_as_linhas.append(linha + [nome_origem])

    # Se capturou os CSVs individuais
    else:
        print("📂 Processando CSVs individuais capturados da rede...")
        for nome_arquivo, conteudo in arquivos_baixados.items():
            linhas_texto = conteudo.splitlines()
            if linhas_texto:
                separador = ";" if ";" in linhas_texto[0] else ","
                leitor = csv.reader(linhas_texto, delimiter=separador)
                linhas = list(leitor)
                if linhas:
                    if cabecalho is None:
                        cabecalho = linhas[0] + ["origem_tabela"]
                    nome_origem = os.path.splitext(nome_arquivo)[0]
                    for linha in linhas[1:]:
                        if linha:
                            todas_as_linhas.append(linha + [nome_origem])

    # Salva o CSV final unificado
    with open(caminho_csv_final, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        if cabecalho:
            escritor.writerow(cabecalho)
        escritor.writerows(todas_as_linhas)

    print(f"✅ CSV final unificado criado com {len(todas_as_linhas)} linhas!")
    return caminho_csv_final

def enviar_para_postgres(caminho_csv):
    print("🐘 Conectando ao PostgreSQL (Supabase) via DuckDB...")
    
    url_banco = os.getenv("URL_BANCO")
    if not url_banco:
        raise ValueError("A variável de ambiente URL_BANCO não foi encontrada.")

    url_banco = url_banco.strip().strip("'").strip('"')
    url_banco = re.sub(r'[\[\]]', '', url_banco)
    
    if "&ipv6=" in url_banco or "?ipv6=" in url_banco:
        url_banco = re.split(r'[&?]ipv6=', url_banco)[0]

    if "sslmode" not in url_banco:
        url_banco += "&sslmode=require" if "?" in url_banco else "?sslmode=require"

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    
    print("🔌 Anexando banco Supabase...")
    con.execute(f"ATTACH '{url_banco}' AS meu_postgres (TYPE POSTGRES);")

    print("📊 Atualizando tabela no Supabase...")
    con.execute("DROP TABLE IF EXISTS meu_postgres.dados_cnj_processos;")
    con.execute(f"""
        CREATE TABLE meu_postgres.dados_cnj_processos AS 
        SELECT * FROM read_csv_auto('{caminho_csv}');
    """)

    print("🏆 PROCESSO FINALIZADO! Todos os dados capturados foram unificados e salvos.")

if __name__ == "__main__":
    arquivo_unificado = rodar_automacao()
    enviar_para_postgres(arquivo_unificado)
