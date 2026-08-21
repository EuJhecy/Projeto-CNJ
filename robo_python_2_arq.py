import os
import re
import csv
import io
import duckdb
from datetime import datetime
from playwright.sync_api import sync_playwright

csvs_capturados = {}

def espiar_resposta(response):
    # Intercepta respostas da rede que sejam arquivos CSV ou exportações de dados
    url = response.url.lower()
    content_type = response.headers.get("content-type", "").lower()
    
    if ".csv" in url or "text/csv" in content_type or "application/csv" in content_type:
        try:
            if response.status == 200:
                # Extrai o nome do arquivo da URL ou usa um identificador
                nome_arquivo = url.split("/")[-1].split("?")[0]
                if not nome_arquivo.endswith(".csv"):
                    nome_arquivo = f"tabela_{len(csvs_capturados) + 1}.csv"
                
                texto = response.text()
                csvs_capturados[nome_arquivo] = texto
                print(f"⚡ Tabela CSV capturada da rede: {nome_arquivo}")
        except Exception:
            pass

def rodar_automacao():
    print("🚀 Iniciando automação de captura e empilhamento dos CSVs...")
    
    pasta_download = os.path.abspath("./downloads")
    os.makedirs(pasta_download, exist_ok=True)
    caminho_csv_final = os.path.join(pasta_download, "dados_cnj_unificados.csv")

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
        
        print("⏳ Aguardando carregamento completo dos dados (60s)...")
        page.wait_for_timeout(60000)

        frame_principal = page.get_by_text("Este navegador não tem").content_frame
        try:
            print("🖱️ Interagindo com a aba de Downloads...")
            frame_principal.get_by_role("button", name="Downloads").click()
            page.wait_for_timeout(15000)
        except Exception as e:
            print(f"Aviso na interação: {e}")

        browser.close()

    # Processamento e empilhamento dos CSVs capturados
    print("📂 Empilhando todos os CSVs capturados...")
    
    cabecalho = None
    todas_as_linhas = []

    if not csvs_capturados:
        raise Exception("Nenhum arquivo CSV foi capturado durante a navegação.")

    for nome_arquivo, conteudo_texto in csvs_capturados.items():
        print(f"  📄 Processando: {nome_arquivo}")
        # Detecta separador (esperado ';')
        linhas_texto = conteudo_texto.splitlines()
        if not linhas_texto:
            continue
            
        separador = ";" if ";" in linhas_texto[0] else ","
        leitor = csv.reader(linhas_texto, delimiter=separador)
        linhas = list(leitor)

        if not linhas:
            continue

        # Define o cabeçalho base na primeira leitura
        if cabecalho is None:
            cabecalho = linhas[0] + ["origem_tabela"]

        nome_limpo = os.path.splitext(nome_arquivo)[0]
        for linha in linhas[1:]:
            if linha:
                todas_as_linhas.append(linha + [nome_limpo])

    # Salva o arquivo final unificado
    with open(caminho_csv_final, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        if cabecalho:
            escritor.writerow(cabecalho)
        escritor.writerows(todas_as_linhas)

    print(f"✅ CSV unificado criado com {len(todas_as_linhas)} registros em: {caminho_csv_final}")
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

    print("📊 Criando a tabela no Supabase (se não existir)...")
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS meu_postgres.dados_cnj_processos AS 
        SELECT * FROM read_csv_auto('{caminho_csv}') LIMIT 0;
    """)

    print("📥 Inserindo registros empilhados no Supabase...")
    con.execute(f"""
        INSERT INTO meu_postgres.dados_cnj_processos 
        SELECT * FROM read_csv_auto('{caminho_csv}');
    """)

    print("🏆 PROCESSO FINALIZADO! Todos os CSVs empilhados e salvos no Supabase.")

if __name__ == "__main__":
    arquivo_unificado = rodar_automacao()
    enviar_para_postgres(arquivo_unificado)
