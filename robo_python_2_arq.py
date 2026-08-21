import os
import re
import csv
import zipfile
import duckdb
from datetime import datetime
from playwright.sync_api import sync_playwright

def rodar_automacao():
    print("🚀 Iniciando automação de download do ZIP...")
    
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
            locale="pt-BR",
            accept_downloads=True
        )
        page = context.new_page()

        print("🌐 Acessando o painel do CNJ...")
        page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/", wait_until="domcontentloaded", timeout=90000)
        
        print("⏳ Aguardando carregamento do painel (45s)...")
        page.wait_for_timeout(45000)

        frame_principal = page.get_by_text("Este navegador não tem").content_frame
        
        # Intercepta e escuta a ação de download nativa do navegador
        with page.expect_download(timeout=60000) as download_info:
            try:
                print("🖱️ Clicando no botão de Download...")
                frame_principal.get_by_role("button", name="Downloads").click()
            except Exception as e:
                print(f"Tentando clique alternativo no botão: {e}")
                frame_principal.get_by_text("Downloads").click()

        download = download_info.value
        caminho_zip = os.path.join(pasta_download, download.suggested_filename)
        download.save_as(caminho_zip)
        print(f"📦 Arquivo ZIP baixado com sucesso: {caminho_zip}")

        browser.close()

    # Processamento e unificação dos CSVs dentro do ZIP
    print("📂 Extraindo e empilhando os arquivos CSV do ZIP...")
    
    cabecalho = None
    todas_as_linhas = []

    with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
        for nome_arquivo in zip_ref.namelist():
            if nome_arquivo.endswith('.csv'):
                print(f"  📄 Processando tabela: {nome_arquivo}")
                with zip_ref.open(nome_arquivo) as f:
                    # Lê o CSV decodificando latin-1 / utf-8 com separador ';'
                    conteudo = f.read().decode('utf-8-sig', errors='ignore').splitlines()
                    leitor = csv.reader(conteudo, delimiter=';')
                    
                    linhas = list(leitor)
                    if not linhas:
                        continue

                    # Define o cabeçalho na primeira leitura
                    if cabecalho is None:
                        cabecalho = linhas[0] + ["origem_tabela"]

                    # Adiciona os dados registrando a tabela de origem
                    nome_limpo = os.path.splitext(nome_arquivo)[0]
                    for linha in linhas[1:]:
                        if linha:  # ignora linhas vazias
                            todas_as_linhas.append(linha + [nome_limpo])

    # Grava o CSV unificado usando vírgula como separador padrão
    with open(caminho_csv_final, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        if cabecalho:
            escritor.writerow(cabecalho)
        escritor.writerows(todas_as_linhas)

    print(f"✅ CSV unificado criado com {len(todas_as_linhas)} registros: {caminho_csv_final}")
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

    print("📊 Criando/Recriando a tabela unificada no Supabase...")
    # Cria a tabela dinamicamente a partir do layout real das colunas do CSV
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS meu_postgres.dados_cnj_processos AS 
        SELECT * FROM read_csv_auto('{caminho_csv}') LIMIT 0;
    """)

    print("📥 Inserindo todas as tabelas empilhadas no Supabase...")
    con.execute(f"""
        INSERT INTO meu_postgres.dados_cnj_processos 
        SELECT * FROM read_csv_auto('{caminho_csv}');
    """)

    print("🏆 PROCESSO FINALIZADO! Todos os dados empilhados no Supabase.")

if __name__ == "__main__":
    arquivo_unificado = rodar_automacao()
    enviar_para_postgres(arquivo_unificado)
