import os
import re
import csv
import zipfile
import duckdb
from datetime import datetime
from playwright.sync_api import sync_playwright

def rodar_automacao():
    print("🚀 Iniciando automação com foco na captura da tag de Blob...")
    
    pasta_download = os.path.abspath("./downloads")
    os.makedirs(pasta_download, exist_ok=True)
    caminho_csv_final = os.path.join(pasta_download, "dados_cnj_unificados.csv")
    caminho_zip = os.path.join(pasta_download, "CJF.zip")

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
        
        print("⏳ Aguardando carregamento do painel (40s)...")
        page.wait_for_timeout(40000)

        # Injeta um script na página para forçar a captura do link 'blob' quando ele for criado
        page.evaluate("""
            window.blobDownloadUrl = null;
            const originalCreateElement = document.createElement;
            document.createElement = function(tagName) {
                const element = originalCreateElement.call(document, tagName);
                if (tagName.toLowerCase() === 'a') {
                    const originalSetAttribute = element.setAttribute;
                    element.setAttribute = function(name, value) {
                        if (name === 'download' || (name === 'href' && value.startswith('blob:'))) {
                            window.blobDownloadUrl = element.href;
                        }
                        return originalSetAttribute.apply(this, arguments);
                    };
                }
                return element;
            };
        """)

        frame = page.get_by_text("Este navegador não tem").content_frame

        print("🖱️ Clicando na aba Downloads para disparar a criação do Blob...")
        
        # Escuta o evento de download atrelado à tag <a>
        with page.expect_download(timeout=90000) as download_info:
            try:
                frame.get_by_role("button", name="Downloads").click()
            except Exception:
                frame.get_by_text("Downloads").click()

        download = download_info.value
        download.save_as(caminho_zip)
        print(f"📦 Sucesso! Arquivo '{download.suggested_filename}' capturado do Blob: {caminho_zip}")

        browser.close()

    # Processamento e empilhamento dos 6 CSVs dentro do CJF.zip
    print("📂 Extraindo e empilhando as 6 tabelas do CJF.zip...")
    
    cabecalho = None
    todas_as_linhas = []

    with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
        for nome_arquivo in zip_ref.namelist():
            if nome_arquivo.endswith('.csv'):
                print(f"  📄 Processando: {nome_arquivo}")
                with zip_ref.open(nome_arquivo) as f:
                    conteudo = f.read().decode('utf-8-sig', errors='ignore').splitlines()
                    leitor = csv.reader(conteudo, delimiter=';')
                    
                    linhas = list(leitor)
                    if not linhas:
                        continue

                    if cabecalho is None:
                        cabecalho = linhas[0] + ["origem_tabela"]

                    nome_origem = os.path.splitext(os.path.basename(nome_arquivo))[0]
                    
                    for linha in linhas[1:]:
                        if linha:
                            todas_as_linhas.append(linha + [nome_origem])

    with open(caminho_csv_final, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        if cabecalho:
            escritor.writerow(cabecalho)
        escritor.writerows(todas_as_linhas)

    print(f"✅ CSV final consolidado com {len(todas_as_linhas)} registros gerado!")
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

    print("🏆 PROCESSO FINALIZADO! Todos os 6 arquivos do CJF.zip salvos com sucesso.")

if __name__ == "__main__":
    arquivo_unificado = rodar_automacao()
    enviar_para_postgres(arquivo_unificado)
