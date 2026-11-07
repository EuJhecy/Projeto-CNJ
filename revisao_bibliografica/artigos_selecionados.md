# Referências - Predição, Prescrição e Otimização no Judiciário

Estudos selecionados para avaliação da relevância em relação ao projeto. 

**Observação:** Os estudos considerados mais diretamente relacionados aos objetivos do projeto estão identificados com ⭐

1. ⭐ **Predicting the number of days in court cases using artificial intelligence** (2022)
   → Predição da duração de processos judiciais utilizando Inteligência Artificial.
   **Link:** https://doi.org/10.1371/journal.pone.0269008

   **Objetivo:** Prever o número de dias necessários para que um magistrado profira uma sentença em um Tribunal Regional do Trabalho, considerando o período entre a conclusão do processo para decisão e a publicação da sentença.

   **Modelos utilizados:** Foram avaliados diferentes algoritmos de aprendizado de máquina, incluindo Multilayer Perceptron (MLP), Gradient Boosting Regressor (GBR), AdaBoost, Support Vector Regression (SVR) e diferentes combinações de modelos por meio da técnica de Stacking. Também foi utilizada a ferramenta SHAP para identificar quais variáveis mais influenciam as previsões.

   **Resultados obtidos:** O AdaBoost apresentou o melhor desempenho, com um coeficiente de determinação (R²) de 0,819 e acurácia de 84% na classificação dos processos por faixas de duração. A análise com SHAP mostrou que o magistrado responsável e o órgão julgador são os fatores que mais influenciam o tempo necessário para a sentença.


2. ⭐ **Investigation of lawsuit process duration using machine learning and process mining** (2024)
   → Utiliza Machine Learning e Process Mining para analisar e prever a duração de processos e identificar gargalos.
   **Link:** https://doi.org/10.1007/s44257-024-00015-0

      **Objetivo:** Investigar o uso combinado de aprendizado de máquina e mineração de processos para prever o tempo de duração de processos trabalhistas brasileiros na fase de execução, considerando os diferentes caminhos percorridos durante a tramitação.

     **Modelos utilizados**: Foram aplicadas técnicas de mineração de processos, como K-means, Agrupamento Hierárquico Aglomerativo e ActiTraC, para identificar padrões nas movimentações processuais. As informações obtidas foram utilizadas em modelos preditivos de Regressão Linear, Support Vector Regression (SVR) e DART, uma variação do Gradient Boosting.

     **Resultados obtidos:** O modelo DART apresentou o melhor desempenho, com R² de 0,875 e erro absoluto médio (MAE) de 316,58 dias, superando o SVR (R² = 0,852) e a Regressão Linear (R² = 0,731). A inclusão das informações obtidas pela mineração de processos melhorou o desempenho preditivo, aumentando o R² de 0,77 para 0,873.

  
3.  ⭐ **The inefficiency of courts of justice: industry structure, capacity and misallocation** (2024)
   → Analisa capacidade judicial, utilização de recursos e alocação de recursos por meio de um modelo de otimização.
   **Link:** https://doi.org/10.1007/s11123-024-00731-5

      **Objetivo:** Analisar como a estrutura dos tribunais, a disponibilidade de recursos e a distribuição de magistrados influenciam a duração dos processos judiciais na Itália. O estudo também busca avaliar quais mudanças na organização e na gestão dos tribunais poderiam reduzir o tempo de tramitação.    
   
      **Modelos utilizados:** O estudo utilizou modelos de otimização matemática, baseados na Análise Envoltória de Dados (DEA), para avaliar a eficiência dos tribunais italianos, considerando a quantidade de magistrados, servidores e processos pendentes. Também foram aplicados modelos econométricos, incluindo regressões com Efeitos Fixos (FE), Efeitos Aleatórios (RE) e Variáveis Instrumentais (2SLS), para analisar como a redução do tempo de tramitação influencia a demanda por novos processos.

      **Resultados obtidos:** O modelo de Efeitos Fixos (FE) apresentou elasticidade da demanda de -0,495 para processos cíveis e -0,182 para processos criminais, com significância estatística (p < 0,01). Já o modelo de Variáveis Instrumentais (2SLS) apresentou elasticidades de -1,107 para processos cíveis e -0,324 para criminais.
   
      O modelo de Efeitos Fixos (FE) foi o escolhido como referência no estudo. Entretanto, não é possível afirmar que ele apresentou o melhor desempenho preditivo apenas com base nas elasticidades, pois esses valores medem a sensibilidade da demanda ao tempo de tramitação, e não a precisão dos modelos
   

4. ⭐ **LegalAnalytics: bridging visual explanations and workload streamline in Brazilian Supreme Court appeals** (2025)
   → Utiliza Machine Learning e explicabilidade para apoiar a análise e gestão da carga de trabalho no STF.
   **Link:** https://doi.org/10.1007/s10506-025-09446-w

   **Objetivo:** Desenvolver um sistema capaz de classificar automaticamente Recursos Extraordinários (RE) encaminhados ao Supremo Tribunal Federal (STF), de acordo com os Temas de Repercussão Geral. O sistema também busca apresentar explicações visuais para facilitar a análise dos processos e auxiliar o trabalho dos gabinetes.

   **Modelos utilizados**: O sistema utilizou principalmente Regressão Logística com representação textual TF-IDF e calibração por Platt Scaling. Também foi aplicada a técnica LIME para destacar os trechos dos documentos que mais contribuíram para as classificações. Além disso, foram avaliados outros algoritmos, como XGBoost, LightGBM, Random Forest, AdaBoost, Decision Tree, Naive Bayes, KNN, SVM e BERT.

   **Resultados obtidos:** O sistema apresentou bom desempenho na classificação dos processos, alcançando valores de Average Precision (AUPRC) superiores a 80% na maioria dos 30 temas analisados, com resultados próximos de 100% em alguns casos. As explicações geradas pelo LIME também receberam avaliações positivas de especialistas jurídicos

5. ⭐ **Improving the trial efficiency of criminal cases with the assistance of artificial intelligence** (2025)
    → Analisa a utilização de Inteligência Artificial para melhorar a eficiência dos julgamentos.
    **Link:** https://doi.org/10.1007/s44163-025-00353-2

   **Objetivo:** Investigar como a inteligência artificial pode contribuir para tornar o julgamento de processos criminais mais rápido e preciso, reduzindo o tempo de tramitação e a ocorrência de erros nas decisões.

   **Modelos utilizados:** Foram utilizados algoritmos de Regressão por Árvores de Decisão (Decision Tree Regression) e Máquinas de Vetores de Suporte (SVM), além de técnicas de Processamento de Linguagem Natural (NLP), com modelos LSTM e Transformers. Essas técnicas foram aplicadas à previsão de prazos, à extração de informações dos processos e à geração automatizada de minutas.

   **Resultados obtidos:** O sistema de inteligência artificial, que combina os modelos Decision Tree Regression, SVM, LSTM e Transformers, apresentou uma acurácia inicial de 85%, alcançando 90% após a otimização dos parâmetros. Sua aplicação reduziu o tempo médio de julgamento dos processos criminais de 45 para 27,67 horas, representando uma redução de aproximadamente 40% em comparação com os métodos tradicionais. Os modelos também contribuíram para agilizar atividades específicas, como a organização de informações (75%), a análise de provas (73,33%) e a geração de sugestões de sentença (80%). Além disso, o uso da IA foi associado a uma redução de 55% nos erros de julgamento, com a taxa global de erros passando de 9% para 3%.

   O estudo, entretanto, não apresentou métricas individuais que permitissem identificar qual dos algoritmos obteve o melhor desempenho.
   

7.  **Maximizando a eficiência judicial: uma proposta de alocação ótima de juízes e varas do 1º grau do TJBA via otimização** (2025)
   → Propõe um modelo de otimização para alocação de juízes e varas do TJBA.
   **Link:** https://hdl.handle.net/1884/100440

8. **Hybrid machine learning modelling with explainability for predicting case delays and durations in Indian lower courts** (2026)
   → Predição de atrasos e duração de processos utilizando modelos de Machine Learning com explicabilidade.
   **Link:** https://doi.org/10.1186/s40537-025-01340-1

9. **Justice in time: A theory of constraints approach** (2023)
   → Analisa gargalos e estratégias para melhorar o fluxo e reduzir o tempo de processamento judicial.
   **Link:** https://doi.org/10.1002/joom.1234


10. **Big-Data Measurement-Model Research about Judges’ Actual Workload in China** (2021)
   → Utiliza Big Data e Machine Learning para mensurar a carga de trabalho dos magistrados.
   **Link:** https://doi.org/10.1017/als.2019.31

11. **Algorithms, efficiency and the two faces of courts: A case study of the Brazilian Superior Court of Justice (STJ)** (2022)
    → Analisa a utilização de algoritmos e seus impactos na eficiência do Superior Tribunal de Justiça (STJ).
    **Link:** https://doi.org/10.1515/sosys-2021-0014 **ou** https://research-api.cbs.dk/ws/portalfiles/portal/96236615/luisa_hedler_algorithms_efficiency_and_the_two_faces_acceptedversion.pdf
