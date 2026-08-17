import pandas as pd
from datetime import datetime
import re
from playwright.sync_api import Playwright, sync_playwright, expect
import os
from sqlalchemy import create_engine


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=True) #HEADLESS = True tira o navegador. Baixa os dados em segundo plano
    context = browser.new_context()
    page = context.new_page()


    # CONECTANDO AO BANCO DE DADOS
    URL_BANCO = os.getenv("URL_BANCO")
    engine = create_engine(URL_BANCO)
  
    # IR PRA PÁGINA DE DOWNLOAD
    page.goto("https://justica-em-numeros.cnj.jus.br/painel-estatisticas/")

    # DEFINIÇÃO DO FRAME PRINCIPAL DO POWER BI
    painel_powerbi = page.get_by_text("Este navegador não tem").content_frame

    # IR ATÉ A ABA DE DOWNLOADS
    painel_powerbi.get_by_role("button", name="Downloads").click()

    # DATA DE HOJE
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
    painel_powerbi.locator(
        "div:nth-child(7) > .vcBody > .visualWrapper > visual-modern > .visual > .slicer-container >\
        .slicer-content-wrapper > .slicer-dropdown-menu > .dropdown-chevron"
    ).click()
    
    
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
    
        # SALVAR O ARQUIVO LOCALMENTE
        nome_do_arquivo = f"dados_tribunal_{nome_tribunal[i-1]}_{hoje}.zip" # os dados vêm do painel compactados
        download.save_as(nome_do_arquivo)

        #DESMARCAR O TRIBUNAL ATUAL ANTES DE IR PARA O PRÓXIMO
        painel_powerbi.locator(".slicerCheckbox.selected > .glyphicon").click()
    
        # LER E TRATAR COM PANDAS
        caminho_temporario = download.path() # ler caminho temporário do arquivp
        df = pd.read_csv(caminho_temporario, compression='zip') # ler arquivo csv diretamente mesmo que esteja compactado
        df['data_ref'] = hoje # add coluna data_ref


        # ENVIA ARQUIVO DO PANDAS PRO BD
        df.to_sql('dados_cnj', con=engine, if_exists="append", index=False)
 

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
