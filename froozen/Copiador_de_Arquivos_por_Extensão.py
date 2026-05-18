import os
import shutil
import streamlit as st

#----------------------------------
# Copiador por Extensão
#----------------------------------
st.title("Copiador de Arquivos por Extensão")
st.caption("Copia todos arquivos das subpastas de uma pasta mãe, por extensão")

#----------------------------------
# Input da Extensão
#----------------------------------
extensao = st.selectbox('Selecione a extensão dos arquivo a serem copiados', (".xlsx", ".xls", ".csv", ".txt", ".pdf", ".TAB", ".zip", ".rar"))

#----------------------------------
# Função para limpar as aspas que podem ser incluídas ao copiar o caminho
#----------------------------------
def clean_path(path):
    return path.strip('"')

#----------------------------------
# Inputs do usuário para os caminhos dos arquivos
#----------------------------------
source_path = clean_path(st.text_input('Caminho para a pasta mãe'))  # O caminho da pasta mãe
output_file_path = clean_path(st.text_input('Caminho para a pasta de saída'))  # O caminho onde o arquivo processado será salvo

#----------------------------------
# Função para copiar os arquivos
#----------------------------------
def copiar_arquivos(source_path, output_file_path):
    # Verificação dos caminhos
    if not os.path.exists(source_path):
        st.error("O caminho da pasta mãe não existe.")
        return
    
    if not os.path.exists(output_file_path):
        try:
            os.makedirs(output_file_path)
            st.info(f"A pasta de destino não existia, então foi criada: {output_file_path}")
        except Exception as e:
            st.error(f"Erro ao criar a pasta de destino: {e}")
            return
    
    arquivos_copiados = 0
    arquivos_falha = 0
    arquivos_encontrados = False
    lista_arquivos = []
    
    # Inicializa o progresso
    num_arquivos = sum([len(files) for r, d, files in os.walk(source_path)])
    progress = st.progress(0)
    progresso_atual = 0
    
    # Percorre o diretório de origem e suas subpastas
    for root, dirs, files in os.walk(source_path):
        for file in files:
            if file.endswith(extensao):
                arquivos_encontrados = True
                caminho_completo = os.path.join(root, file)
                destino_completo = os.path.join(output_file_path, file)
                
                try:
                    shutil.copy2(caminho_completo, destino_completo)
                    arquivos_copiados += 1
                    lista_arquivos.append(f"Arquivo copiado: {file}")
                except Exception as e:
                    arquivos_falha += 1
                    lista_arquivos.append(f"Erro ao copiar {file}: {e}")
            
            progresso_atual += 1
            progress.progress(progresso_atual / num_arquivos)
    
    # Verifica se nenhum arquivo foi encontrado
    if not arquivos_encontrados:
        st.warning(f"Não há arquivos com a extensão {extensao} na pasta mãe.")
    else:
        # Exibe o resumo da operação
        st.success(f"Cópia concluída: {arquivos_copiados} arquivos copiados.")
        if arquivos_falha > 0:
            st.warning(f"{arquivos_falha} arquivos não puderam ser copiados.")
        
        # Adiciona CSS customizado para ajustar o layout do expander
        st.markdown(
            """
            <style>
            div.st-expanderContent {
                width: 100% !important;
                max-height: 300px; /* Define um limite de altura com scroll */
                overflow-y: auto; /* Ativa o scroll quando necessário */
            }
            </style>
            """, unsafe_allow_html=True
        )
        
        # Exibe a lista de arquivos copiados dentro de um expander com scroll
        with st.expander("Clique para ver os detalhes dos arquivos copiados"):
            for arquivo in lista_arquivos:
                st.write(arquivo)

#----------------------------------
# Centraliza apenas o botão
#----------------------------------
st.markdown(
    """
    <style>
    div.stButton > button {
        display: block;
        margin-left: auto;
        margin-right: auto;
    }
    </style>
    """, unsafe_allow_html=True
)

# Coloca a função de copiar dentro do bloco do botão
if st.button('Copiar arquivos', type='primary'):
    copiar_arquivos(source_path, output_file_path)
