import os
import csv
import zipfile
import re
import duckdb
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from playwright.sync_api import sync_playwright

def rodar_automacao():
    print("🚀 1. Iniciando navegador e preparando download do CJF.zip...")
    
    pasta_download = "./downloads"
    os.makedirs(pasta_download, exist_ok=True)
    caminho_zip = os.path.join(pasta_download, "CJF.zip")
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
        
        print("⏳ Aguardando renderização dos componentes (40s)...")
        page.wait_for_timeout(40000)

        frame = page.get_by_text("Este navegador não tem").content_frame

        print("🖱️ Clicando na aba Downloads e capturando o arquivo ZIP...")
        
        # O expect_download captura o arquivo ZIP gerado via Blob pelo Power BI
        with page.expect_download(timeout=90000) as download_info:
            try:
                frame.get_by_role("button", name="Downloads").click()
            except Exception:
                frame.get_by_text("Downloads").click()

        download = download_info.value
        download.save_as(caminho_zip)
        print(f"📦 Sucesso! Arquivo '{download.suggested_filename}' baixado em: {caminho_zip}")

        browser.close()

    # --- UNIFICAÇÃO DOS 6 CSVs REAIS ---
    print("📂 2. Extraindo e empilhando os 6 CSVs do CJF.zip...")
    
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

                    # Define cabeçalho e insere a coluna 'origem_tabela'
                    if cabecalho is None:
                        cabecalho = linhas[0] + ["origem_tabela"]

                    nome_origem = os.path.splitext(os.path.basename(nome_arquivo))[0]

                    for linha in linhas[1:]:
                        if linha:
                            todas_as_linhas.append(linha + [nome_origem])

    # Grava o CSV unificado real
    with open(caminho_csv_final, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if cabecalho:
            writer.writerow(cabecalho)
        writer.writerows(todas_as_linhas)

    print(f"✅ CSV final consolidado com {len(todas_as_linhas)} linhas reais!")
    return caminho_csv_final


def enviar_para_postgres(caminho_csv):
    print("🐘 3. Conectando ao PostgreSQL (Supabase) via DuckDB...")
    
    url_banco = os.getenv("URL_BANCO")
    if not url_banco:
        raise ValueError("A variável de ambiente URL_BANCO não foi encontrada.")

    # Tratamento da URL para compatibilidade com DuckDB
    parsed = urlparse(url_banco)
    query_params = parse_qs(parsed.query)
    
    params_validos = {}
    if "sslmode" in query_params:
        params_validos["sslmode"] = query_params["sslmode"][0]
    else:
        params_validos["sslmode"] = "require"

    new_query = urlencode(params_validos)
    url_limpa = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    
    print("🔌 Anexando banco Supabase...")
    con.execute(f"ATTACH '{url_limpa}' AS meu_postgres (TYPE POSTGRES);")

    print("📊 Recriando a tabela no Supabase com os microdados completos...")
    con.execute("DROP TABLE IF EXISTS meu_postgres.dados_cnj_processos;")
    con.execute(f"CREATE TABLE meu_postgres.dados_cnj_processos AS SELECT * FROM read_csv_auto('{caminho_csv}');")

    print("🏆 PROCESSO FINALIZADO! Todos os dados dos 6 arquivos salvos com sucesso.")

if __name__ == "__main__":
    arquivo_unificado = rodar_automacao()
    enviar_para_postgres(arquivo_unificado)
