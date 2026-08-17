import pandas as pd
from datetime import datetime
import re
from playwright.sync_api import Playwright, sync_playwright, expect
import os
from sqlalchemy import create_engine


def run(playwright: Playwright) -> None:
    # 1. Configura navegador com resolução HD para garantir renderização dos elementos
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1366, "height": 768})
    page = context.new_page()

    # CONEXÃO BANCO
    URL_BANCO = os.getenv("URL_BANCO")
    if not URL_BANCO:
        raise ValueError("A variável de ambiente 'URL_BANCO' não foi encontrada!")
    engine = create_engine(URL_BANCO)

    # 2. Navega e aguarda estabilização da rede
    page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(5000)  # Pausa de segurança para o Power BI inicializar

    # 3. Localiza o iframe principal do Power BI
    frame_element = page.wait_for_selector("iframe", timeout=60000)
    painel_powerbi = frame_element.content_frame()

    # 4. Aguarda e clica na aba de Downloads
    btn_downloads = painel_powerbi.get_by_role("button", name="Downloads")
    btn_downloads.wait_for(state="visible", timeout=60000)
    btn_downloads.click()
    page.wait_for_timeout(3000)

    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # LISTA DOS 92 TRIBUNAIS
    nome_tribunal = ['CJF','STJ','STM','TJAC','TJAL','TJAM','TJAP','TJBA','TJCE','TJDFT',
                       'TJES','TJGO','TJMA','TJMG','TJMMG','TJMRS','TJMS','TJMSP','TJMT',
                       'TJPA','TJPB','TJPE','TJPI','TJPR','TJRJ','TJRN','TJRO','TJRR','TJRS',
                       'TJSC','TJSE','TJSP','TJTO','TRE-AC','TRE-AL','TRE-AM','TRE-AP',
                       'TRE-BA','TRE-CE','TRE-DF','TRE-ES','TRE-GO','TRE-MA','TRE-MG',
                       'TRE-MS','TRE-MT','TRE-PA','TRE-PB','TRE-PE','TRE-PI','TRE-PR',
                       'TRE-RJ','TRE-RN','TRE-RO','TRE-RR','TRE-RS','TRE-SC','TRE-SE',
                       'TRE-SP','TRE-TO','TRF1','TRF2','TRF3','TRF4','TRF5','TRF6','TRT1',
                       'TRT10','TRT11','TRT12','TRT13','TRT14','TRT15','TRT16','TRT17',
                       'TRT18','TRT19','TRT2','TRT20','TRT21','TRT22','TRT23','TRT24',
                       'TRT3','TRT4','TRT5','TRT6','TRT7','TRT8','TRT9','TSE','TST']

    # CLICAR NA LISTA DO PAINEL PARA FAZER O DOWNLOAD
    lista_tribunais_pbi = "div:nth-child(7) > .vcBody > .visualWrapper > visual-modern > .visual > .slicer-container > .slicer-content-wrapper > .slicer-dropdown-menu > .dropdown-chevron"

    # PARA ESPERAR O ELEMENTO FICAR PRONTO ANTES DE CLICAR
    painel_powerbi.locator(lista_tribunais_pbi).wait_for(state="visible", timeout=60000) #timeout em milissegundos (60s)

    # CLIQUE COM UM TEMPO DE TOLERÂNCIA MAIOR (60s)
    painel_powerbi.locator(lista_tribunais_pbi).click(timeout=60000)
    
    
    # LOOP PARA BAIXSAR OS 92 ARQUIVOS
    for i in range(1,93):
        
        posicao_tribunal = i+1
        
        # CLICAR NO TRIBUNAL
        painel_powerbi.locator(
            f"div:nth-child({posicao_tribunal}) > .slicerItemContainer > .slicerCheckbox > .glyphicon"
        ).click()
    
        # BAIXAR ARQUIVO
        with page.expect_download() as download_info:
            painel_powerbi.frame_locator('iframe[name="visual-sandbox"]').locator("#sandbox-host").click()
    
        download = download_info.value
    
        # SALVAR O ARQUIVO LOCALMENTE COM NOME PERSONALIZADO
        nome_do_arquivo = f"dados_tribunal_{nome_tribunal[i-1]}_{hoje}.zip" # os dados vêm do painel compactados
        download.save_as(nome_do_arquivo)

        #DESMARCAR O TRIBUNAL ATUAL ANTES DE IR PARA O PRÓXIMO
        painel_powerbi.locator(".slicerCheckbox.selected > .glyphicon").click()
    
        # LER E TRATAR COM PANDAS
        caminho_temporario = download.path() # ler caminho temporário do arquivp
        df = pd.read_csv(nome_do_arquivo, compression='zip') # ler arquivo csv diretamente mesmo que esteja compactado
        df['data_ref'] = hoje # add coluna data_ref

        # ENVIA ARQUIVO DO PANDAS PRO BD
        df.to_sql('dados_cnj', con=engine, if_exists="append", index=False)

        # LIMPA O ARQUIVO ZIP LOCAL PARA NÃO ENCHER O DISCO DA MÁQUINA VIRTUAL
        if os.path.exists(nome_do_arquivo):
            os.remove(nome_do_arquivo)
 

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
