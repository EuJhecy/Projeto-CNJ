import json
import os
import duckdb
from datetime import datetime
from playwright.sync_api import sync_playwright

# 1. Criamos uma "caixinha" (lista) para guardar os dados que o site vai enviar
dados_capturados = []

# 2. Esta função é o nosso "escutador". Ela olha tudo o que o site baixa na internet
def espiar_rede(resposta):
    # Se o site baixar algo que tem "querydata" no nome (é o arquivo do Power BI)
    if "querydata" in resposta.url and resposta.status == 200:
        print("🎉 Achei os dados do Power BI na rede!")
        try:
            # Pega esses dados em formato JSON e guarda na nossa caixinha
            dados_json = resposta.json()
            dados_capturados.append(dados_json)
        except:
            pass

# 3. Aqui começa a execução do Robô
print("🚀 Iniciando o robô...")

with sync_playwright() as p:
    # Abre o navegador de forma invisível
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Manda a página ficar "espiando" a rede usando a função que criamos acima
    page.on("response", espiar_rede)

    print("🌐 Entrando no site do CNJ...")
    # Entra no site sem travar no carregamento
    page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/", wait_until="domcontentloaded")

    print("⏳ Esperando 40 segundos para o Power BI carregar os dados...")
    # Espera o painel carregar sozinho na tela
    page.wait_for_timeout(40000)

    # Fecha o navegador
    browser.close()

# 4. Salvar os dados capturados em um arquivo no computador/GitHub
if len(dados_capturados) > 0:
    os.makedirs("./dados", exist_ok=True)
    caminho_arquivo = "./dados/cnj_dados.json"
    
    # Salva os dados em um arquivo .json
    with open(caminho_arquivo, "w", encoding="utf-8") as f:
        json.dump(dados_capturados, f)
    
    print("✅ Dados salvos com sucesso em arquivo!")
else:
    print("❌ Não conseguimos pegar os dados. Tente rodar novamente.")
    exit() # Encerra o programa se não pegou nada

# 5. Enviar os dados para o seu Banco de Dados PostgreSQL
print("🐘 Conectando ao PostgreSQL para salvar os dados...")

# Pega o link do banco que você cadastrou no GitHub Secrets (ou usa uma string local)
url_banco = os.getenv("URL_BANCO")

# Usa o DuckDB para enviar o arquivo salvo direto pro Postgres
con = duckdb.connect()
con.execute("INSTALL postgres; LOAD postgres;")
con.execute(f"ATTACH '{url_banco}' AS meu_postgres (TYPE POSTGRES);")

# Cria a tabela no banco e insere os dados automaticamente
con.execute("""
    CREATE TABLE IF NOT EXISTS meu_postgres.dados_cnj AS 
    SELECT * FROM read_json_auto('./dados/cnj_dados.json');
""")

print("🏆 PROCESSO FINALIZADO! Dados estão salvos no seu PostgreSQL.")
