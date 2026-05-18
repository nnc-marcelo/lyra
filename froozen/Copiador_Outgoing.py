import streamlit as st
import os
import shutil
import pandas as pd

#----------------------------------
# Copiador de Arquivos Mensais para Outgoing
#----------------------------------

# Título da aplicação
st.title("Copiador de Arquivos Mensais para Outgoing")
descritivo = st.caption("Copia todos os relatórios do mês para fins contábeis.")

#----------------------------------
# Variáveis configuráveis - Entrada pelo usuário
#----------------------------------

caminho_excel = st.text_input("Caminho para a planilha RR:", r'Z:\FINANCEIRO\03. ROYALTY\02. REVENUE RECONCILIATION\2024 Revenue Reconciliation.xlsx')
coluna_caminho = 'Stmt Path'
coluna_catalogo = 'Catalog'
coluna_fonte_renda = 'Income Source'
coluna_mes_pgto = 'Mês Pgto'
pasta_saida = st.text_input("Caminho para a pasta de saída:")
mes = st.number_input("Mês de Pagamento:", min_value=1, max_value=12, value=1, step=1)

# Substituir raiz da rede
raiz_antiga = st.text_input("Raiz origem:", r'N:')
raiz_nova = st.text_input("Raiz saída:", r'Z:')

#----------------------------------
# Função para copiar arquivos
#----------------------------------

def copiar_arquivos(row):
    caminhos_arquivos = row[coluna_caminho].split('/')
    catalogo = row[coluna_catalogo].strip()
    fonte_renda = row[coluna_fonte_renda].strip()
    pasta_destino = os.path.join(pasta_saida, catalogo, fonte_renda)

    # Criar a pasta de destino se não existir
    if not os.path.exists(pasta_destino):
        os.makedirs(pasta_destino)

    # Copiar os arquivos
    for caminho_arquivo in caminhos_arquivos:
        caminho_arquivo = caminho_arquivo.strip().replace(raiz_antiga, raiz_nova)
        try:
            shutil.copy(caminho_arquivo, pasta_destino)
            st.write(f"Arquivo {caminho_arquivo} copiado para {pasta_destino}")
        except FileNotFoundError:
            st.warning(f"Arquivo {caminho_arquivo} não encontrado.")
        except Exception as e:
            st.error(f"Erro ao copiar o arquivo {caminho_arquivo}: {e}")

#----------------------------------
# Botão para iniciar a cópia dos arquivos
#----------------------------------

col1, col2, col3 = st.columns([1.6,1,1.6])

with col2:

    if st.button("Iniciar Cópia", type='primary'):
        # Ler o arquivo Excel
        try:
            df = pd.read_excel(caminho_excel, sheet_name='ROYALTY')
            df_mes = df[df[coluna_mes_pgto] == mes].dropna(subset=[coluna_caminho])

            # Iterar sobre o DataFrame e copiar os arquivos
            df_mes.apply(copiar_arquivos, axis=1)
            st.success("Processo de cópia concluído!")
        except FileNotFoundError:
            st.error("O arquivo Excel especificado não foi encontrado.")
        except Exception as e:
            st.error(f"Erro ao processar o arquivo Excel: {e}")