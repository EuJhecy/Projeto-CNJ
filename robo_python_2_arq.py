import os
import json
import duckdb
from datetime import datetime
from playwright.sync_api import sync_playwright

# Caixinha para guardar todas as respostas da API
respostas_powerbi = []

def espiar_resposta(response):
    """Escuta e captura requisições de dados da API do Power BI"""
    if "querydata" in response.url or "conceptualschema" in response.url:
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

        # Ativa o escutador de rede
        page.on("response", espiar_resposta)

        print("🌐 Acessando o painel do CNJ...")
        page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/", wait_until="domcontentloaded", timeout=90000)
        
        # Aguarda o Power BI carregar o painel e disparar as requisições de dados
        print("⏳ Aguardando carregamento dos dados de fundo (45s)...")
        page.wait_for_timeout(45000)

        # Navega até a aba Downloads para garantir o disparo da consulta específica
        frame_principal = page.get_by_text("Este navegador não tem").content_frame
        try:
            frame_principal.get_by_role("button", name="Downloads").click()
            page.wait_for_timeout(15000)
        except Exception as e:
            print(f"Aviso ao clicar na aba: {e}")

        browser.close()

    if not respostas_powerbi:
        raise Exception("Nenhuma requisição de dados foi capturada do Power BI.")

    # Salva os dados num arquivo intermediário
    caminho_json = os.path.join(pasta_download, "payload_bruto.json")
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(respostas_powerbi, f, ensure_ascii=False)

    print(f"✅ Payload capturado e salvo em: {caminho_json}")

    # Converte o JSON estruturado do Power BI em um CSV limpo via DuckDB
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT * FROM read_json_auto('{caminho_json}')
        ) TO '{caminho_csv}' (HEADER, DELIMITER ',');
    """)

    print(f"✅ Arquivo CSV gerado com sucesso: {caminho_csv}")
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

    print("📊 Importando dados para a tabela no banco...")
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS meu_postgres.dados_cnj_processos AS 
        SELECT * FROM read_csv_auto('{caminho_csv}', ignore_errors=true);
    """)

    print("🏆 PROCESSO FINALIZADO! Dados gravados com sucesso no Supabase.")

if __name__ == "__main__":
    arquivo_baixado = rodar_automacao()
    enviar_para_postgres(arquivo_baixado)
