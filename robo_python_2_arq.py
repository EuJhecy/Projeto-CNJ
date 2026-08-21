import os
import csv
import zipfile
import re
import duckdb
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from playwright.sync_api import sync_playwright

def encontrar_e_clicar_cjf(page):
    """Procura pelo elemento/botão 'CJF' na página principal e em todos os frames."""
    # Primeiro tenta na página e frames conhecidos
    frames_para_testar = [page] + page.frames
    
    for f in frames_para_testar:
        try:
            # Tenta localizar por texto exato ou parcial
            elemento = f.get_by_text("CJF", exact=True)
            if elemento.count() > 0:
                print("🎯 Botão 'CJF' localizado com sucesso!")
                elemento.first.click(force=True)
                return True
        except Exception:
            continue

    # Fallback: busca por seletor de texto em todos os frames
    for f in frames_para_testar:
        try:
            loc = f.locator("text=CJF")
            if loc.count() > 0:
                print("🎯 Botão 'CJF' localizado via locator!")
                loc.first.click(force=True)
                return True
        except Exception:
            continue

    raise Exception("Não foi possível localizar o botão 'CJF' na tela de downloads.")

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
        
        print("⏳ Aguardando renderização inicial do painel (40s)...")
        page.wait_for_timeout(40000)

        print("🖱️ Passo 1: Clicando na aba 'Downloads'...")
        clicou_downloads = False
        for f in [page] + page.frames:
            try:
                btn = f.get_by_role("button", name="Downloads")
                if btn.count() > 0:
                    btn.click(force=True)
                    clicou_downloads = True
                    break
                else:
                    txt = f.get_by_text("Downloads")
                    if txt.count() > 0:
                        txt.first.click(force=True)
                        clicou_downloads = True
                        break
            except Exception:
                continue

        if not clicou_downloads:
            print("⚠️ Aviso: Aba Downloads não localizada pelos métodos padrão, tentando continuar...")

        print("⏳ Aguardando renderização da página de downloads (15s)...")
        page.wait_for_timeout(15000)

        print("🖱️ Passo 2: Clicando na opção 'CJF' para disparar o download real...")
        
        # O expect_download aguarda a criação do arquivo após o clique no CJF
        try:
            with page.expect_download(timeout=90000) as download_info:
                encontrar_e_clicar_cjf(page)

            download = download_info.value
            download.save_as(caminho_zip)
            print(f"📦 Sucesso! Arquivo '{download.suggested_filename}' capturado em: {caminho_zip}")
        finally:
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
