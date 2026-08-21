import os
import csv
import zipfile
import re
import duckdb
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from playwright.sync_api import sync_playwright

def rodar_automacao():
    print("🚀 1. Iniciando automação do CNJ via Playwright...")
    
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
        
        print("⏳ Aguardando o iframe do Power BI carregar (35s)...")
        page.wait_for_timeout(35000)

        # Localiza o frame principal do Power BI
        frame_pbi = None
        for f in page.frames:
            if "powerbi.com" in f.url or "Este navegador não tem" in f.content():
                frame_pbi = f
                break

        if not frame_pbi:
            frame_pbi = page.main_frame

        print("🖱️ Passo 1: Clicando na aba 'Downloads'...")
        # Tenta clicar no botão Downloads dentro do frame
        try:
            frame_pbi.get_by_role("button", name="Downloads").click(timeout=10000, force=True)
        except Exception:
            try:
                frame_pbi.get_by_text("Downloads").first.click(timeout=10000, force=True)
            except Exception as e:
                print(f"Aviso na navegação para Downloads: {e}")

        print("⏳ Aguardando renderização das opções de download (15s)...")
        page.wait_for_timeout(15000)

        print("🖱️ Passo 2: Clicando no cartão 'CJF' e aguardando o arquivo ZIP...")
        
        # Dispara o expect_download e clica no elemento CJF
        download_sucesso = False
        try:
            with page.expect_download(timeout=60000) as download_info:
                # Procura o texto CJF em todos os frames ativos
                clicou_cjf = False
                for f in [frame_pbi] + page.frames:
                    try:
                        elem = f.get_by_text("CJF", exact=False)
                        if elem.count() > 0:
                            elem.first.click(force=True)
                            clicou_cjf = True
                            print("🎯 Clique no elemento 'CJF' realizado com sucesso!")
                            break
                    except Exception:
                        continue

                if not clicou_cjf:
                    raise Exception("Elemento visual 'CJF' não foi encontrado na tela.")

            download = download_info.value
            download.save_as(caminho_zip)
            print(f"📦 Pacote ZIP baixado com sucesso em: {caminho_zip}")
            download_sucesso = True
        except Exception as e:
            print(f"❌ Erro ao capturar download: {e}")

        browser.close()

    if not download_sucesso or not os.path.exists(caminho_zip):
        raise FileNotFoundError("Falha na captura do arquivo CJF.zip do painel do CNJ.")

    # --- UNIFICAÇÃO DOS 6 CSVs REAIS ---
    print("📂 2. Extraindo e empilhando os CSVs do CJF.zip...")
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

    # Grava o CSV unificado final
    with open(caminho_csv_final, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if cabecalho:
            writer.writerow(cabecalho)
        writer.writerows(todas_as_linhas)

    print(f"✅ CSV final consolidado com {len(todas_as_linhas)} linhas!")
    return caminho_csv_final


def enviar_para_postgres(caminho_csv):
    print("🐘 3. Conectando ao PostgreSQL (Supabase) via DuckDB...")
    
    url_banco = os.getenv("URL_BANCO")
    if not url_banco:
        raise ValueError("A variável de ambiente URL_BANCO não foi encontrada.")

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

    print("📊 Recriando a tabela com os dados unificados no Supabase...")
    con.execute("DROP TABLE IF EXISTS meu_postgres.dados_cnj_processos;")
    con.execute(f"CREATE TABLE meu_postgres.dados_cnj_processos AS SELECT * FROM read_csv_auto('{caminho_csv}');")

    print("🏆 PROCESSO FINALIZADO! Todos os microdados do CJF foram gravados com sucesso.")


if __name__ == "__main__":
    arquivo_unificado = rodar_automacao()
    enviar_para_postgres(arquivo_unificado)
