import streamlit as st
import pandas as pd
import io
import os
from pathlib import Path

def main():
    st.title("Warner Music TXT to Excel")
    st.caption("Converte os arquivos .txt da Warner Music em arquivos .xlsx") 
    # Upload do arquivo
    uploaded_file = st.file_uploader("Faça upload do arquivo TXT", type=['txt'])
    
    if uploaded_file is not None:
        try:
            # Lê o arquivo
            df = pd.read_csv(uploaded_file, sep='\t')
            
            # Mostra os dados
            # st.subheader("Visualização dos dados")
            # st.dataframe(df)
            
            # Prepara o arquivo Excel para download
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            
            # Configura o botão de download
            excel_data = output.getvalue()
            
            # Gera nome do arquivo de saída baseado no arquivo de entrada
            output_filename = Path(uploaded_file.name).stem + '_PYTHON.xlsx'
                 
            st.download_button(
                label="📥 Baixar arquivo processado",
                data=excel_data,
                file_name=output_filename,
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
            # Mensagem de sucesso
            st.success('Arquivo processado com sucesso! Clique no botão acima para baixar.')
            
        except Exception as e:
            st.error(f'Erro ao processar o arquivo: {str(e)}')

if __name__ == '__main__':
    main()