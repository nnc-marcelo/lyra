import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

def create_download_section(df_processed, original_filename):
    """Função para criar a seção de download"""
    st.subheader("Download do Arquivo Processado")
    
    if original_filename.endswith('.csv'):
        # Para CSV
        csv_data = df_processed.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV Processado",
            data=csv_data,
            file_name=f"processado_{original_filename}",
            mime="text/csv"
        )
    else:
        # Para Excel
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_processed.to_excel(writer, index=False, sheet_name='Processado')
        
        st.download_button(
            label="📥 Download Excel Processado",
            data=buffer.getvalue(),
            file_name=f"processado_{original_filename}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def show_comparison_and_download(df_original, df_processed, selected_column, filename):
    """Função para mostrar comparação e seção de download"""
    # Mostrar comparação
    st.subheader("Comparação dos Resultados")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Total Original:**")
        st.write(f"Total: {df_original[selected_column].sum():,.2f}")
    
    with col2:
        st.write("**Total Processado:**")
        st.write(f"Total: {df_processed[selected_column].sum():,.2f}")
        difference = df_original[selected_column].sum() - df_processed[selected_column].sum()
        st.write(f"Diferença: {difference:,.2f}")
    
    # Exibir dados processados
    st.subheader("Dados Processados")
    st.dataframe(df_processed, use_container_width=True)
    
    # Download do arquivo processado
    create_download_section(df_processed, filename)

def main():
    st.title("Processador de Descontos")
    st.divider()
    
    # Upload de arquivo
    uploaded_file = st.file_uploader(
        "Selecione o arquivo de royalties",
        type=['csv', 'xlsx', 'xls'],
        help="Formatos suportados: CSV, Excel (.xlsx, .xls)"
    )
    
    if uploaded_file is not None:
        # Leitura do arquivo
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.success(f"Arquivo carregado com sucesso! {len(df)} linhas encontradas.")
            
            # Exibir preview dos dados
            st.subheader("Preview dos Dados")
            st.dataframe(df.head(), use_container_width=True)
            
            # Identificar colunas numéricas
            numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()
            
            if not numeric_columns:
                st.warning("Nenhuma coluna numérica encontrada no arquivo.")
                return
            st.divider()

            # Seleção da coluna para cálculos
            st.subheader("Configuração dos Cálculos")
            selected_column = st.selectbox(
                "Selecione a coluna numérica para os cálculos:",
                numeric_columns
            )
            
            if selected_column:
                # Mostrar soma da coluna selecionada
                total_sum = df[selected_column].sum()
                st.write(f"Total da coluna **{selected_column}**: {total_sum:,.2f}")
                
                # Funcionalidade de desconto - ESTRUTURA UNIFICADA
                st.subheader("Desconto Proporcional")
                
                discount_type = st.radio(
                    "Tipo de desconto:",
                    ["Percentual", "Valor específico", "Adicionar Linha de Desconto"]
                )
                
                if discount_type == "Percentual":
                    st.caption("Aplica um percentual de desconto em cada linha individualmente")
                    
                    discount_value = st.number_input(
                        "Percentual de desconto (%):",
                        min_value=0.0,
                        max_value=100.0,
                        value=0.0,
                        step=0.1,
                        format="%.2f"
                    )
                    
                    # Botão para aplicar desconto percentual
                    if st.button("Aplicar Desconto", type="primary"):
                        df_processed = df.copy()
                        df_processed[selected_column] = df[selected_column] * (1 - discount_value/100)
                        st.success(f"Desconto de {discount_value}% aplicado com sucesso!")
                        
                        # Mostrar comparação e download
                        show_comparison_and_download(df, df_processed, selected_column, uploaded_file.name)
                
                elif discount_type == "Valor específico":
                    st.caption("Distribui um valor fixo de desconto proporcionalmente entre todas as linhas")
                    
                    discount_value = st.number_input(
                        "Valor total de desconto:",
                        min_value=0.0,
                        value=0.0,
                        step=0.01,
                        format="%.2f"
                    )
                    
                    # Botão para aplicar desconto por valor específico
                    if st.button("Aplicar Desconto", type="primary"):
                        total_original = df[selected_column].sum()
                        if total_original > 0:
                            df_processed = df.copy()
                            proportion_factor = (total_original - discount_value) / total_original
                            df_processed[selected_column] = df[selected_column] * proportion_factor
                            st.success(f"Desconto de {discount_value:,.2f} aplicado proporcionalmente!")
                            
                            # Mostrar comparação e download
                            show_comparison_and_download(df, df_processed, selected_column, uploaded_file.name)
                        else:
                            st.error("Não é possível aplicar desconto: soma da coluna é zero ou negativa.")
                
                elif discount_type == "Adicionar Linha de Desconto":
                    st.caption("Adiciona uma nova linha com ajuste (mantém valores originais intactos)")
                    
                    # Seleção da coluna para descrição
                    text_columns = df.select_dtypes(include=['object', 'string']).columns.tolist()
                    if not text_columns:
                        st.warning("Nenhuma coluna de texto encontrada para a descrição.")
                    else:
                        description_column = st.selectbox(
                            "Selecione a coluna para a descrição do ajuste:",
                            text_columns
                        )
                        
                        # Tipo de ajuste
                        adjustment_type = st.radio(
                            "Tipo de ajuste:",
                            ["Desconto (reduz o total)", "Ajuste positivo (aumenta o total)"]
                        )
                        
                        # Campos para a nova linha
                        col1, col2 = st.columns(2)
                        with col1:
                            adjustment_description = st.text_input(
                                "Descrição do ajuste:",
                                value="Desconto aplicado" if adjustment_type.startswith("Desconto") else "Ajuste positivo",
                                help="Texto que aparecerá na linha de ajuste"
                            )
                        
                        with col2:
                            adjustment_amount = st.number_input(
                                "Valor do ajuste:",
                                min_value=0.0,
                                value=0.0,
                                step=0.01,
                                format="%.2f",
                                help="Digite sempre valor positivo - o sinal será aplicado automaticamente"
                            )
                        
                        # Botão para adicionar linha de ajuste
                        if st.button("Aplicar Desconto", type="primary"):
                            if adjustment_amount > 0 and adjustment_description.strip():
                                df_processed = df.copy()
                                
                                # Determinar o valor final com sinal correto
                                final_value = -adjustment_amount if adjustment_type.startswith("Desconto") else adjustment_amount
                                
                                # Criar nova linha
                                new_row = {}
                                for col in df_processed.columns:
                                    if col == selected_column:
                                        new_row[col] = final_value
                                    elif col == description_column:
                                        new_row[col] = adjustment_description
                                    else:
                                        new_row[col] = ""  # Células vazias para outras colunas
                                
                                # Adicionar a nova linha
                                df_processed = pd.concat([df_processed, pd.DataFrame([new_row])], ignore_index=True)
                                
                                # Mensagem de sucesso personalizada
                                action_text = "Desconto" if adjustment_type.startswith("Desconto") else "Ajuste positivo"
                                st.success(f"{action_text} adicionado: {adjustment_description} - R$ {adjustment_amount:,.2f}")
                                
                                # Mostrar comparação e download
                                show_comparison_and_download(df, df_processed, selected_column, uploaded_file.name)
                            
                            else:
                                st.error("Por favor, preencha a descrição e um valor maior que zero.")
        
        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {str(e)}")

if __name__ == "__main__":
    main()