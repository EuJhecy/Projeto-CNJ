import os
import csv
import zipfile
import re
import urllib.request
import duckdb
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from playwright.sync_api import sync_playwright

url_zip_encontrada = []

def capturar_link_download(request):
    """Monitora a rede para pegar qualquer link de download de ZIP/Blob do CJF"""
    url = request.url
    if ("blob:" in url or ".zip" in url or "export" in url) and "cjf" in url.lower():
        url_zip_encontrada.append(url)
        print(f"🎯 URL de download capturada da rede: {url}")

def rodar_automacao():
    print("🚀 1. Iniciando navegação rápida no CNJ...")
    
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            locale="pt-BR",
            accept_downloads=True
        )
        page = context.new_page()
        page.on("request", capturar_link_download)

        print("🌐 Acessando o painel do CNJ...")
        page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/", wait_until="domcontentloaded", timeout=60000)
        
        # Reduzido para apenas 20s para o Power BI carregar
        print("⏳ Aguardando renderização do painel (20s)...")
        page.wait_for_timeout(20000)

        print("🖱️ Clicando na aba 'Downloads'...")
        for f in [page] + page.frames:
            try:
                btn = f.get_by_role("button", name="Downloads")
                if btn.count() > 0:
                    btn.click(force=True)
                    break
                else:
                    txt = f.get_by_text("Downloads")
                    if txt.count() > 0:
                        txt.first.click(force=True)
                        break
            except Exception:
                continue

        print("⏳ Aguardando o disparo do download (10s)...")
        
        # Tenta pegar via evento nativo com timeout curto (15s)
        try:
            with page.expect_download(timeout=15000) as download_info:
                # Tenta um clique rápido no CJF se visível
                for f in [page] + page.frames:
                    try:
                        f.get_by_text("CJF").first.click(timeout=3000)
                        break
                    except Exception:
                        pass
            download = download_info.value
            download.save_as(caminho_zip)
            print("📦 Pacote ZIP capturado via evento nativo!")
        except Exception:
            print("⚠️ Evento padrão de download não disparou. Verificando links capturados...")

        browser.close()

    # Se o download nativo não salvou o arquivo, mas pegamos a URL da rede
    if not os.path.exists(caminho_zip) and url_zip_encontrada:
        print("📥 Baixando arquivo via requisição direta...")
        urllib.request.urlretrieve(url_zip_encontrada[0], caminho_zip)

    if not os.path.exists(caminho_zip):
        raise FileNotFoundError("Não foi possível baixar o arquivo CJF.zip.")

    # --- UNIFICAÇÃO DOS CSVs ---
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

    with open(caminho_csv_final, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if cabecalho:
            writer.writerow(cabecalho)
        writer.writerows(todas_as_linhas)

    print(f"✅ CSV final consolidado com {len(todas_as_linhas)} linhas!")
    return caminho_csv_final


def enviar_para_postgres(caminho_csv):
    print("🐘 3. Conectando ao Supabase via DuckDB...")
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

    print("📊 Recriando a tabela com os dados unificados...")
    con.execute("DROP TABLE IF EXISTS meu_postgres.dados_cnj_processos;")
    con.execute(f"CREATE TABLE meu_postgres.dados_cnj_processos AS SELECT * FROM read_csv_auto('{caminho_csv}');")

    print("🏆 PROCESSO FINALIZADO com sucesso!")

if __name__ == "__main__":
    arquivo_unificado = rodar_automacao()
    enviar_para_postgres(arquivo_unificado)
