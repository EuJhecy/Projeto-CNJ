import os
import duckdb
from datetime import datetime
from playwright.sync_api import sync_playwright

def rodar_automacao():
    print("🚀 Iniciando o robô de download do CNJ...")
    
    pasta_download = "./downloads"
    os.makedirs(pasta_download, exist_ok=True)
    caminho_csv = os.path.join(pasta_download, "dados_cnj.csv")

    with sync_playwright() as p:
        # Configuração para rodar no servidor do GitHub Actions sem travar
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            accept_downloads=True
        )
        page = context.new_page()

        print("🌐 Acessando o painel...")
        page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(15000) # Pausa para o Power BI carregar

        # Identifica o iframe principal do Power BI
        frame_principal = page.get_by_text("Este navegador não tem").content_frame

        print("🖱️ Navegando pelas abas do Power BI...")
        frame_principal.get_by_role("button", name="Downloads").click()
        page.wait_for_timeout(5000)

        # Clica no filtro do menu
        frame_principal.locator("i").nth(4).click()
        page.wait_for_timeout(2000)

        # Seleciona a opção do filtro
        frame_principal.locator("div:nth-child(2) > .slicerItemContainer > .slicerCheckbox > .glyphicon").click()
        page.wait_for_timeout(3000)

        print("⏳ Clicando para baixar o arquivo...")
        
        # Localiza o elemento do sandbox com mais tolerância
        iframe_sandbox = frame_principal.locator("visual-container-group").filter(
            has_text="Pressionar Enter para explorar os dadosLista de Processos por"
        ).locator("iframe[name=\"visual-sandbox\"]").content_frame
        
        botao_exportar = iframe_sandbox.locator("#sandbox-host")
        
        # Espera o botão estar pronto no DOM por até 2 minutos
        botao_exportar.wait_for(state="attached", timeout=120000)

        # Dispara o download usando force=True
        with page.expect_download(timeout=120000) as download_info:
            botao_exportar.click(force=True, timeout=120000)
        
        download = download_info.value
        download.save_as(caminho_csv)
        print(f"✅ CSV baixado com sucesso em: {caminho_csv}")

        context.close()
        browser.close()

    return caminho_csv

def enviar_para_postgres(caminho_csv):
    print("🐘 Conectando ao PostgreSQL (Supabase) via DuckDB...")
    
    url_banco = os.getenv("URL_BANCO")
    if not url_banco:
        raise ValueError("A variável de ambiente URL_BANCO não foi encontrada.")

    # Adiciona a regra de SSL caso não esteja na URL
    if "sslmode" not in url_banco:
        url_banco += "&sslmode=require" if "?" in url_banco else "?sslmode=require"

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{url_banco}' AS meu_postgres (TYPE POSTGRES);")

    print("📊 Importando CSV para a tabela no banco...")
    # O DuckDB lê o CSV baixado e cria/atualiza a tabela no Supabase
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS meu_postgres.dados_cnj_processos AS 
        SELECT * FROM read_csv_auto('{caminho_csv}');
    """)

    print("🏆 PROCESSO FINALIZADO! Dados gravados com sucesso no banco de dados.")

if __name__ == "__main__":
    arquivo_baixado = rodar_automacao()
    enviar_para_postgres(arquivo_baixado)
