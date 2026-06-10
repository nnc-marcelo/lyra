import streamlit as st
import pandas as pd
import io
import base64
from typing import List, Dict

def check_column_consistency(dfs: List[pd.DataFrame]) -> Dict:
    """Verifica se todos os DataFrames têm as mesmas colunas"""
    all_columns = set(dfs[0].columns)
    inconsistencies = {}
    
    for i, df in enumerate(dfs[1:], 2):
        missing_cols = all_columns - set(df.columns)
        extra_cols = set(df.columns) - all_columns
        
        if missing_cols or extra_cols:
            inconsistencies[i] = {
                'missing': list(missing_cols),
                'extra': list(extra_cols)
            }
    
    return inconsistencies

def read_file(file, sep=',', decimal='.', thousands=','):
    """Lê arquivo com parâmetros personalizados"""
    file_extension = file.name.split('.')[-1].lower()
    
    if file_extension == 'csv':
        encodings = ['utf-8', 'latin1', 'iso-8859-1']
        for encoding in encodings:
            try:
                return pd.read_csv(
                    file,
                    encoding=encoding,
                    sep=sep,
                    decimal=decimal,
                    thousands=thousands
                )
            except UnicodeDecodeError:
                continue
        st.error(f"Não foi possível ler o arquivo {file.name}. Tente converter para UTF-8.")
        return None
    
    elif file_extension in ['xlsx', 'xls']:
        return pd.read_excel(file)
    
    else:
        st.error(f"Formato de arquivo não suportado: {file_extension}")
        return None

def get_download_link(df):
    """Gera bytes do arquivo Excel para download"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def get_possible_aggregations():
    """Retorna lista de agregações possíveis"""
    return [
        # 'Soma', 'Média', 'Mediana', 'Mínimo', 'Máximo', 'Contagem',
        # 'Desvio Padrão', 'Primeiro', 'Último'
        'Soma', 'Contagem', 'Média', 'Mínimo', 'Máximo'
       
    ]

def apply_aggregation(df, column, agg_type):
    """Aplica agregação selecionada"""
    agg_map = {
        'Soma': 'sum',
        'Média': 'mean',
        'Mediana': 'median',
        'Mínimo': 'min',
        'Máximo': 'max',
        'Contagem': 'count',
        'Desvio Padrão': 'std',
        'Primeiro': 'first',
        'Último': 'last'
    }
    
    try:
        result = df[column].agg(agg_map[agg_type])
        return f"{agg_type} de {column}: {result:.2f}"
    except:
        return f"Não foi possível calcular {agg_type} para {column}"

def main():
    st.title('Conversor CSV')
    
    st.caption("""
    ### Instruções:
    1. Faça upload do arquivo.
   
    """)
    
    # 2. Extensões aceitas: xlsx/ xls/ csv
    # 3. Os arquivos devem ter a mesma estrutura de colunas


    # Configurações para arquivos CSV
    with st.expander("Configurações para arquivos CSV"):
        col1, col2, col3 = st.columns(3)
        with col1:
            sep = st.selectbox(
                "Separador",
                [',', ';', '|', '\t'],
                index=0
            )
        with col2:
            decimal = st.selectbox(
                "Decimal",
                ['.', ','],
                index=0
            )
        with col3:
            thousands = st.selectbox(
                "Separador de Milhar",
                [',', '.', ' ', ''],
                index=0
            )
    
    # Upload múltiplo de arquivos
    uploaded_files = st.file_uploader(
        "Adicione os arquivos",
        type=['csv'],
        accept_multiple_files=True
    )

    #'xlsx', 'xls', 
    
    if uploaded_files:
        dfs = []
        all_columns = set()
        
        # Primeira passagem: coletar todas as colunas
        for file in uploaded_files:
            df = read_file(file, sep, decimal, thousands)
            if df is not None:
                all_columns.update(df.columns)
                dfs.append(df)
        
        if dfs:
            # Verificar consistência das colunas
            inconsistencies = check_column_consistency(dfs)
            
            if inconsistencies:
                st.error("### Estrutura de colunas inconsistente!")
                for df_num, issues in inconsistencies.items():
                    st.write(f"Arquivo {df_num}:")
                    if issues['missing']:
                        st.write("Colunas faltantes:", ", ".join(issues['missing']))
                    if issues['extra']:
                        st.write("Colunas extras:", ", ".join(issues['extra']))
                st.stop()
            
            # Concatenar todos os DataFrames
            final_df = pd.concat(dfs, ignore_index=True)
            
            st.divider()

            st.write("##### Resultados da concatenação:")
            st.write(f"Qntd de arquivos: {len(uploaded_files)}")
            st.write(f"Total de linhas: {len(final_df)}")
            st.write(f"Total de colunas: {len(final_df.columns)}")
            
            st.divider()

            # Seleção de coluna e agregação
            col1, col2 = st.columns(2)
            with col1:
                selected_column = st.selectbox(
                    "Selecione a coluna para agregação",
                    options=final_df.columns
                )
            with col2:
                selected_agg = st.selectbox(
                    "Selecione a agregação",
                    options=get_possible_aggregations()
                )
            
            if selected_column and selected_agg:
                st.text(apply_aggregation(final_df, selected_column, selected_agg))
            
            # Botão para download com estilo primário
            col1, col2, col3 = st.columns(3)
            with col2:

                excel_data = get_download_link(final_df)
                st.download_button(
                    label="Baixar arquivo concatenado",
                    data=excel_data,
                    file_name="arquivos_concatenados.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type='primary'
                )

if __name__ == '__main__':
    main()