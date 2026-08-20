import os
import json
import csv
import duckdb
from datetime import datetime
from playwright.sync_api import sync_playwright

respostas_powerbi = []

def espiar_resposta(response):
    if "querydata" in response.url:
        try:
            if response.status == 200:
                dados = response.json()
                respostas_powerbi.append(dados)
                print("⚡ Dados do Power BI capturados da rede!")
        except Exception:
            pass

def rodar_automacao():
    print("🚀 Iniciando automação via interceptação de API...")
    
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
            locale="pt-BR"
        )
        page = context.new_page()

        page.on("response", espiar_resposta)

        print("🌐 Acessando o painel do CNJ...")
        page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/", wait_until="domcontentloaded", timeout=90000)
        
        print("⏳ Aguardando carregamento dos dados de fundo (45s)...")
        page.wait_for_timeout(45000)

        frame_principal = page.get_by_text("Este navegador não tem").content_frame
        try:
            frame_principal.get_by_role("button", name="Downloads").click()
            page.wait_for_timeout(15000)
        except Exception as e:
            print(f"Aviso ao clicar na aba: {e}")

        browser.close()

    if not respostas_powerbi:
        raise Exception("Nenhuma requisição de dados foi capturada do Power BI.")

    # Processamento e extração nativa em Python
    linhas_extraidas = []
    for payload in respostas_powerbi:
        try:
            results = payload.get("results", [])
            for res in results:
                result = res.get("result", {}).get("data", {}).get("dsr", {}).get("DS", [{}])[0]
                value_dicts = result.get("PH", [{}])[0].get("DM0", [])
                for item in value_dicts:
                    if "G0" in item:
                        linhas_extraidas.append([str(item["G0"])])
        except Exception:
            continue

    # Escreve o CSV usando o módulo csv nativo
    with open(caminho_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["dados_raw"])  # Cabeçalho
        if linhas_extraidas:
            writer.writerows(linhas_extraidas)
        else:
            # Fallback seguro caso o payload venha num formato diferente
            writer.writerow([json.dumps(respostas_powerbi)])

    print(f"✅ CSV estruturado gerado com sucesso: {caminho_csv}")
    return caminho_csv

def enviar_para_postgres(caminho_csv):
    print("🐘 Conectando ao PostgreSQL (Supabase) via DuckDB...")
    
    url_banco = os.getenv("URL_BANCO")
    if not url_banco:
        raise ValueError("A variável de ambiente URL_BANCO não foi encontrada.")

    # Remove parâmetros incompatíveis com o driver C++ do DuckDB Postgres
    if "&ipv6=" in url_banco or "?ipv6=" in url_banco:
        url_banco = url_banco.split("&ipv6=")[0].split("?ipv6=")[0]

    # Garante o parâmetro obrigatório de SSL
    if "sslmode" not in url_banco:
        url_banco += "&sslmode=require" if "?" in url_banco else "?sslmode=require"

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{url_banco}' AS meu_postgres (TYPE POSTGRES);")

    print("📊 Criando a tabela no Supabase (se não existir)...")
    con.execute("CREATE TABLE IF NOT EXISTS meu_postgres.dados_cnj_processos (dados_raw VARCHAR);")

    print("📥 Inserindo os dados do CSV no Supabase...")
    con.execute(f"INSERT INTO meu_postgres.dados_cnj_processos SELECT * FROM read_csv_auto('{caminho_csv}', ignore_errors=true);")

    print("🏆 PROCESSO FINALIZADO! Dados gravados com sucesso no Supabase.")
if __name__ == "__main__":
    arquivo_baixado = rodar_automacao()
    enviar_para_postgres(arquivo_baixado)
