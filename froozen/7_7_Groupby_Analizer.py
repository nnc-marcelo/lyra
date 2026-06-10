import streamlit as st
import pandas as pd
import io
from typing import List, Optional

st.set_page_config(page_title="Royalties GroupBy Analyzer", layout="wide")

st.title("📊 Análise de Relatórios de Royalties")

# Upload de arquivos
uploaded_files = st.file_uploader(
    "Carregue um ou mais arquivos (CSV ou XLSX)",
    type=["csv", "xlsx"],
    accept_multiple_files=True
)

if uploaded_files:
    # Configuração de encoding para CSV
    csv_encoding = st.selectbox(
        "Encoding para arquivos CSV",
        ["utf-8", "latin-1", "iso-8859-1", "cp1252", "utf-16"],
        index=0
    )
    
    # Campo para linha do cabeçalho
    header_row = st.number_input(
        "Linha do cabeçalho (0 = primeira linha)",
        min_value=0,
        value=0,
        step=1
    )
    
    # Verificar planilhas em arquivos Excel
    excel_sheets = {}
    for file in uploaded_files:
        if file.name.endswith(('.xlsx', '.xls')):
            excel_file = pd.ExcelFile(file)
            if len(excel_file.sheet_names) > 1:
                excel_sheets[file.name] = excel_file.sheet_names
    
    # Seletor de planilhas se necessário
    sheet_selections = {}
    if excel_sheets:
        st.subheader("📋 Seleção de Planilhas")
        for filename, sheets in excel_sheets.items():
            sheet_selections[filename] = st.selectbox(
                f"Planilha de '{filename}'",
                options=sheets,
                key=f"sheet_{filename}"
            )
    
    # Carregar arquivos
    dfs = []
    errors = []
    
    for file in uploaded_files:
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file, encoding=csv_encoding, header=header_row)
            else:
                sheet_name = sheet_selections.get(file.name, 0)
                df = pd.read_excel(file, sheet_name=sheet_name, header=header_row)
            dfs.append((file.name, df))
        except Exception as e:
            errors.append(f"{file.name}: {str(e)}")
    
    if errors:
        st.error("Erros ao carregar arquivos:")
        for error in errors:
            st.write(f"- {error}")
    
    if dfs:
        st.success(f"{len(dfs)} arquivo(s) carregado(s) com sucesso")
        
        # Validar estrutura dos dataframes
        if len(dfs) > 1:
            first_cols = set(dfs[0][1].columns)
            mismatches = []
            
            for name, df in dfs[1:]:
                if set(df.columns) != first_cols:
                    mismatches.append(name)
            
            if mismatches:
                st.error(f"❌ Arquivos com estrutura diferente: {', '.join(mismatches)}")
                st.stop()
        
        # Concatenar dataframes
        combined_df = pd.concat([df for _, df in dfs], ignore_index=True)
        st.info(f"Total de registros: {len(combined_df):,}")
        
        # Mostrar preview
        with st.expander("Preview dos dados combinados"):
            st.dataframe(combined_df.head(20))
        
        # Configurações de análise
        st.subheader("⚙️ Configurações de Análise")
        
        col1, col2 = st.columns(2)
        
        with col1:
            groupby_col = st.selectbox(
                "Coluna para agrupar (GroupBy)",
                options=combined_df.columns.tolist()
            )
            
            metric_operation = st.selectbox(
                "Operação",
                options=["Soma", "Média", "Máximo", "Mínimo", "Contagem"]
            )
        
        with col2:
            value_col = st.selectbox(
                "Coluna de valores",
                options=combined_df.columns.tolist(),
                index=min(1, len(combined_df.columns) - 1)
            )
        
        # Filtro
        st.subheader("🔍 Filtros")
        
        unique_values = combined_df[groupby_col].dropna().unique()
        unique_values_sorted = sorted(unique_values.astype(str))
        
        selected_values = st.multiselect(
            f"Filtrar valores em '{groupby_col}' (deixe vazio para todos)",
            options=unique_values_sorted,
            help="Digite para buscar e selecione múltiplos valores"
        )
        
        # Aplicar filtro
        if selected_values:
            filtered_df = combined_df[
                combined_df[groupby_col].astype(str).isin(selected_values)
            ]
            st.info(f"Registros após filtro: {len(filtered_df):,}")
        else:
            filtered_df = combined_df
        
        # Executar análise
        if st.button("🚀 Gerar Análise", type="primary"):
            try:
                # Mapear operações
                operations = {
                    "Soma": "sum",
                    "Média": "mean",
                    "Máximo": "max",
                    "Mínimo": "min",
                    "Contagem": "count"
                }
                
                result_df = filtered_df.groupby(groupby_col)[value_col].agg(
                    operations[metric_operation]
                ).reset_index()
                
                result_df.columns = [groupby_col, f"{metric_operation} de {value_col}"]
                result_df = result_df.sort_values(
                    by=f"{metric_operation} de {value_col}",
                    ascending=False
                )
                
                # Mostrar resultados
                st.subheader("📈 Resultados")
                st.dataframe(
                    result_df,
                    use_container_width=True,
                    height=400
                )
                
                # Estatísticas
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total de grupos", len(result_df))
                with col2:
                    st.metric("Valor total", f"{result_df.iloc[:, 1].sum():,.2f}")
                with col3:
                    st.metric("Valor médio", f"{result_df.iloc[:, 1].mean():,.2f}")
                
                # Download
                csv_buffer = io.StringIO()
                result_df.to_csv(csv_buffer, index=False)
                
                st.download_button(
                    label="⬇️ Download CSV",
                    data=csv_buffer.getvalue(),
                    file_name=f"royalties_analysis_{metric_operation.lower()}.csv",
                    mime="text/csv"
                )
                
            except Exception as e:
                st.error(f"Erro ao processar: {str(e)}")
else:
    st.info("👆 Carregue um ou mais arquivos para começar")