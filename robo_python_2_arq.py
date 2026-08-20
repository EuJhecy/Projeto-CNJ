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
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            accept_downloads=True,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo"
        )
        page = context.new_page()

        try:
            print("🌐 Acessando o painel...")
            page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(10000)

            # Localiza o iframe do relatório do Power BI
            frame_principal = page.frame_locator('iframe[title*="Power BI"], iframe[src*="powerbi"]').first

            print("🖱️ Navegando pelas abas do Power BI...")
            # Clica no botão Downloads
            frame_principal.get_by_role("button", name="Downloads").click()
            page.wait_for_timeout(5000)

            # Filtro do menu
            frame_principal.locator("i").nth(4).click()
            page.wait_for_timeout(2000)

            # Seleciona o checkbox
            frame_principal.locator("div:nth-child(2) > .slicerItemContainer > .slicerCheckbox > .glyphicon").click()
            page.wait_for_timeout(5000)

            print("⏳ Localizando o visual de exportação...")
            
            # Localiza o iframe sandbox dentro do container "Lista de Processos"
            sandbox_frame = (
                frame_principal.locator("visual-container-group")
                .filter(has_text="Lista de Processos")
                .locator("iframe")
                .first
            ).content_frame

            if not sandbox_frame:
                # Fallback caso use frame_locator encadeado
                sandbox_frame_locator = (
                    frame_principal.locator("visual-container-group")
                    .filter(has_text="Lista de Processos")
                    .frame_locator("iframe")
                )
                botao_exportar = sandbox_frame_locator.locator("button, a, [role='button'], #sandbox-host > *").first
            else:
                # Busca pelo elemento clicável interno dentro do sandbox
                botao_exportar = sandbox_frame.locator("button, a, [role='button'], #sandbox-host").first

            botao_exportar.wait_for(state="visible", timeout=60000)

            print("⏳ Disparando o download do arquivo...")
            with page.expect_download(timeout=120000) as download_info:
                try:
                    botao_exportar.click(timeout=10000)
                except Exception:
                    # Se o clique normal for interceptado, força via JavaScript
                    botao_exportar.evaluate("el => el.click()")

            download = download_info.value
            download.save_as(caminho_csv)
            print(f"✅ CSV baixado com sucesso em: {caminho_csv}")

        except Exception as e:
            # Salva screenshot para debug caso falhe no GitHub Actions
            page.screenshot(path="debug_erro_download.png", full_page=True)
            print("❌ Erro durante a automação. Screenshot salvo como 'debug_erro_download.png'")
            raise e
        finally:
            context.close()
            browser.close()

    return caminho_csv

def enviar_para_postgres(caminho_csv):
    print("🐘 Conectando ao PostgreSQL (Supabase) via DuckDB...")
    
    url_banco = os.getenv("URL_BANCO")
    if not url_banco:
        raise ValueError("A variável de ambiente URL_BANCO não foi encontrada.")

    if "sslmode" not in url_banco:
        url_banco += "&sslmode=require" if "?" in url_banco else "?sslmode=require"

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{url_banco}' AS meu_postgres (TYPE POSTGRES);")

    print("📊 Importando CSV para a tabela no banco...")
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS meu_postgres.dados_cnj_processos AS 
        SELECT * FROM read_csv_auto('{caminho_csv}');
    """)

    print("🏆 PROCESSO FINALIZADO! Dados gravados com sucesso no banco de dados.")

if __name__ == "__main__":
    arquivo_baixado = rodar_automacao()
    enviar_para_postgres(arquivo_baixado)
