import streamlit as st
import pandas as pd
from io import BytesIO
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
pd.set_option('display.max_colwidth', None)

#----------------------------------
# Funções auxiliares
#----------------------------------

def detectar_formato_arquivo(file):
    """
    Detecta automaticamente o formato do arquivo Backoffice.
    
    Retorna:
        - 0: arquivo começa direto com o cabeçalho (header=0)
        - 5: arquivo tem metadados nas primeiras linhas (header=5)
        - None: arquivo inválido ou muito pequeno
    """
    try:
        # Tenta ler as primeiras linhas
        df_test = pd.read_excel(file, nrows=7)
        
        # Se o arquivo tem menos de 2 linhas, é inválido
        if len(df_test) < 1:
            return None
        
        # Verifica se a primeira linha já é o cabeçalho correto
        if "BO_PayeesID" in df_test.columns or "PAYEESID" in str(df_test.columns[0]).upper():
            return 0
        
        # Se o arquivo tem pelo menos 6 linhas, tenta com header=5
        if len(df_test) >= 6:
            # Reseta o ponteiro do arquivo
            file.seek(0)
            df_test_h5 = pd.read_excel(file, header=5, nrows=1)
            
            # Verifica se com header=5 encontra o cabeçalho correto
            if "BO_PayeesID" in df_test_h5.columns or any("PAYEE" in str(col).upper() for col in df_test_h5.columns):
                return 5
        
        # Se não detectou formato válido
        return None
        
    except Exception as e:
        return None
    finally:
        # Garante que o ponteiro do arquivo volta ao início
        file.seek(0)


def ler_arquivo_backoffice(file):
    """
    Lê arquivo Backoffice detectando automaticamente o formato.
    
    Retorna:
        - DataFrame com os dados
        - String com informações sobre a leitura
        - Boolean indicando sucesso
    """
    nome_arquivo = file.name
    
    # Detecta o formato
    header_pos = detectar_formato_arquivo(file)
    
    if header_pos is None:
        return None, f"❌ Arquivo muito pequeno ou formato inválido", False
    
    try:
        # Lê o arquivo com o header correto
        df = pd.read_excel(file, header=header_pos)
        
        # Valida se o DataFrame não está vazio
        if len(df) == 0:
            return None, f"⚠️ Arquivo sem dados", False
        
        # Mensagem de sucesso com informações
        info = f"✅ Lido com sucesso (header={header_pos}, {len(df)} linhas)"
        
        return df, info, True
        
    except Exception as e:
        return None, f"❌ Erro ao ler: {str(e)}", False


#----------------------------------
# Interface Streamlit
#----------------------------------

st.title("Concat Backoffice")
st.caption("Concatena e totaliza os arquivos Backoffice para conferência e inclusão no Repertoir.")

# Upload dos arquivos
uploaded_files = st.file_uploader(
    "Faça o upload dos arquivos Excel", 
    type=["xlsx", "xls"], 
    accept_multiple_files=True,
    key="concat_files",
)

if uploaded_files:
    st.info(f"📁 {len(uploaded_files)} arquivo(s) carregado(s)")
    
    # Botões para escolher a ação
    col1, col2 = st.columns(2)
    
    with col1:
        concat_button = st.button('🔗 Concatenar arquivos', type='secondary', use_container_width=True)
    
    with col2:
        totals_button = st.button('🧮 Calcular totais', type='primary', use_container_width=True)
    
    #----------------------------------
    # CONCATENAR ARQUIVOS
    #----------------------------------
    
    if concat_button:
        st.divider()
        st.subheader("📊 Processando concatenação...")
        
        # Lista para armazenar os DataFrames e logs
        dataframes = []
        logs = []
        arquivos_sucesso = 0
        arquivos_erro = 0
        
        # Processamento com barra de progresso
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            progress = (i + 1) / len(uploaded_files)
            progress_bar.progress(progress)
            status_text.text(f"Processando {i+1}/{len(uploaded_files)}: {file.name}")
            
            # Tenta ler o arquivo
            df, info, sucesso = ler_arquivo_backoffice(file)
            
            if sucesso:
                dataframes.append(df)
                logs.append(f"**{file.name}** - {info}")
                arquivos_sucesso += 1
            else:
                logs.append(f"**{file.name}** - {info}")
                arquivos_erro += 1
        
        # Limpa o status
        progress_bar.empty()
        status_text.empty()
        
        # Mostra os logs de processamento
        with st.expander(f"📋 Detalhes do processamento ({arquivos_sucesso} sucesso, {arquivos_erro} erro)", expanded=False):
            for log in logs:
                st.markdown(log)
        
        # Se conseguiu ler algum arquivo
        if dataframes:
            try:
                # Concatena todos os DataFrames
                concatenated_df = pd.concat(dataframes, ignore_index=True)
                
                # Informações sobre o resultado
                st.success(f"""
                ✅ **Concatenação concluída com sucesso!**
                - Arquivos processados: {arquivos_sucesso}/{len(uploaded_files)}
                - Total de linhas: {len(concatenated_df):,}
                - Total de colunas: {len(concatenated_df.columns)}
                """)
                
                # Preview dos dados
                with st.expander("👁️ Visualizar dados concatenados", expanded=False):
                    st.dataframe(concatenated_df.head(100), use_container_width=True)
                
                # Prepara o arquivo para download
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    concatenated_df.to_excel(writer, index=False, sheet_name='Dados Concatenados')
                
                # Botão de download
                st.download_button(
                    label="📥 Baixar arquivo concatenado",
                    data=buffer.getvalue(),
                    file_name="backoffice_concatenado.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"❌ Erro ao concatenar os arquivos: {str(e)}")
        
        else:
            st.error("❌ Nenhum arquivo pôde ser processado com sucesso!")
    
    #----------------------------------
    # CALCULAR TOTAIS
    #----------------------------------
    
    if totals_button:
        st.divider()
        st.subheader("💰 Calculando totais...")
        
        # Lista para armazenar os resultados
        results = []
        arquivos_processados = 0
        arquivos_ignorados = []
        
        # Processamento com barra de progresso
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            progress = (i + 1) / len(uploaded_files)
            progress_bar.progress(progress)
            status_text.text(f"Processando {i+1}/{len(uploaded_files)}: {file.name}")
            
            # Verifica se é um arquivo ST (Statement)
            if "ST" in file.name.upper():
                try:
                    # Tenta detectar o formato e ler
                    df, info, sucesso = ler_arquivo_backoffice(file)
                    
                    if not sucesso:
                        arquivos_ignorados.append((file.name, info))
                        continue
                    
                    # Procura pela coluna de royalties
                    coluna_royalties = None
                    
                    if "ROYALTIES_TO_BE_PAID" in df.columns:
                        coluna_royalties = "ROYALTIES_TO_BE_PAID"
                    elif "ROYALTIES_TO_BE_PAID_$" in df.columns:
                        coluna_royalties = "ROYALTIES_TO_BE_PAID_$"
                    else:
                        # Tenta encontrar coluna que contenha "ROYALTIES" no nome
                        for col in df.columns:
                            if "ROYALTIES" in str(col).upper() and "PAID" in str(col).upper():
                                coluna_royalties = col
                                break
                    
                    if coluna_royalties:
                        total_royalties = df[coluna_royalties].sum()
                        results.append((file.name, total_royalties))
                        arquivos_processados += 1
                    else:
                        arquivos_ignorados.append((file.name, "❌ Coluna de royalties não encontrada"))
                
                except Exception as e:
                    arquivos_ignorados.append((file.name, f"❌ Erro: {str(e)}"))
            else:
                arquivos_ignorados.append((file.name, "⚠️ Não é arquivo ST (Statement)"))
        
        # Limpa o status
        progress_bar.empty()
        status_text.empty()
        
        # Mostra arquivos ignorados
        if arquivos_ignorados:
            with st.expander(f"⚠️ Arquivos ignorados ({len(arquivos_ignorados)})", expanded=False):
                for nome, motivo in arquivos_ignorados:
                    st.markdown(f"**{nome}** - {motivo}")
        
        # Se processou algum arquivo
        if results:
            # Cria o DataFrame com os resultados
            df_results = pd.DataFrame(results, columns=["Arquivo", "Soma de ROYALTIES_TO_BE_PAID"])
            
            # Arredonda os valores para duas casas decimais
            df_results["Soma de ROYALTIES_TO_BE_PAID"] = df_results["Soma de ROYALTIES_TO_BE_PAID"].round(2)
            
            # Calcula o total
            total_royalties_sum = df_results["Soma de ROYALTIES_TO_BE_PAID"].sum().round(2)
            
            # Adiciona uma linha com a soma total
            df_results.loc[len(df_results.index)] = ["TOTAL GERAL", total_royalties_sum]
            
            # Formata como moeda brasileira
            df_results["Soma de ROYALTIES_TO_BE_PAID"] = df_results["Soma de ROYALTIES_TO_BE_PAID"].apply(
                lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
            
            # Exibe o resultado
            st.success(f"✅ {arquivos_processados} arquivo(s) totalizado(s) com sucesso!")
            
            # Mostra a tabela
            st.dataframe(df_results, use_container_width=True, hide_index=True)
            
            # Cálculos adicionais
            st.divider()
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    label="💰 Total Bruto",
                    value=f"R$ {total_royalties_sum:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
            
            desconto_r3 = (total_royalties_sum * 0.025).round(2)
            
            with col2:
                st.metric(
                    label="📉 Desconto R3 (2,5%)",
                    value=f"R$ {desconto_r3:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
            
            total_liquido = (total_royalties_sum - desconto_r3).round(2)
            
            with col3:
                st.metric(
                    label="✅ Total Líquido",
                    value=f"R$ {total_liquido:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
            
            # Botão para baixar os totais
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                # Remove a formatação para salvar os valores numéricos
                df_export = pd.DataFrame(results, columns=["Arquivo", "Total_Royalties"])
                df_export.loc[len(df_export.index)] = ["TOTAL GERAL", total_royalties_sum]
                df_export.loc[len(df_export.index)] = ["Desconto R3 (2,5%)", desconto_r3]
                df_export.loc[len(df_export.index)] = ["TOTAL LÍQUIDO", total_liquido]
                
                df_export.to_excel(writer, index=False, sheet_name='Totais')
            
            st.download_button(
                label="📥 Baixar totais em Excel",
                data=buffer.getvalue(),
                file_name="totais_backoffice.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        else:
            st.error("❌ Nenhum arquivo válido para totalização foi encontrado.")

else:
    st.info("📤 Aguardando upload dos arquivos...")
    st.markdown("""
    ### 📝 Instruções:
    
    **Para Concatenar:**
    - Faça upload de múltiplos arquivos Excel do Backoffice
    - Clique em "🔗 Concatenar arquivos"
    - Baixe o arquivo único com todos os dados
    
    **Para Totalizar:**
    - Faça upload de arquivos **ST** (Statements)
    - Clique em "🧮 Calcular totais"
    - Visualize o resumo financeiro e baixe os totais
    """)