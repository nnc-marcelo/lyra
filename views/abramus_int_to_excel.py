import streamlit as st
import pandas as pd
import io
import base64

from utils.abramus_pdf import ler_internacional
from utils.page import setup_page

def create_download_link(df, filename):
    """Cria um link de download para o arquivo Excel"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # 1. Detalhamento Completo
        df.to_excel(writer, sheet_name='Detalhamento Completo', index=False)

        # 2. Resumo por Música
        resumo_musica = df.groupby(['Título', 'ISRC/ISWC'])['Rendimento'].sum().reset_index()
        resumo_musica = resumo_musica.sort_values('Rendimento', ascending=False)
        resumo_musica.to_excel(writer, sheet_name='Resumo por Música', index=False)

        # 3. Resumo por Sociedade
        resumo_sociedade = df.groupby(['Sociedade', 'Território'])['Rendimento'].sum().reset_index()
        resumo_sociedade = resumo_sociedade.sort_values('Rendimento', ascending=False)
        resumo_sociedade.to_excel(writer, sheet_name='Resumo por Sociedade', index=False)

        # Formatação
        workbook = writer.book
        money_format = workbook.add_format({'num_format': 'R$ #,##0.00'})
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'bg_color': '#D9D9D9',
            'border': 1
        })

        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            if sheet_name == 'Detalhamento Completo':
                worksheet.set_column('A:A', 40)  # Título
                worksheet.set_column('B:B', 15)  # ISRC/ISWC
                worksheet.set_column('C:H', 20)  # Outras colunas
                worksheet.set_column('I:I', 15, money_format)  # Rendimento
            elif sheet_name == 'Resumo por Música':
                worksheet.set_column('A:A', 40)
                worksheet.set_column('B:B', 15)
                worksheet.set_column('C:C', 15, money_format)
            elif sheet_name == 'Resumo por Sociedade':
                worksheet.set_column('A:B', 25)
                worksheet.set_column('C:C', 15, money_format)

    excel_data = output.getvalue()
    b64 = base64.b64encode(excel_data).decode('utf-8')
    return f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">Download do arquivo Excel</a>'


def main():
    setup_page(__file__)

    uploaded_file = st.file_uploader("Faça upload do demonstrativo PDF da ABRAMUS", type="pdf")

    if uploaded_file is not None:
        with st.spinner('Processando o arquivo... Por favor, aguarde.'):
            try:
                df = ler_internacional(uploaded_file)

                st.success("Arquivo processado com sucesso!")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total de registros", len(df))
                with col2:
                    st.metric("Valor total", f"R$ {df['Rendimento'].sum():,.2f}")

                st.subheader("Preview dos dados extraídos")
                st.dataframe(df.head())

                original_filename = uploaded_file.name
                excel_filename = f"{original_filename.rsplit('.', 1)[0]}_PYTHON.xlsx"

                download_link = create_download_link(df, excel_filename)
                st.markdown(download_link, unsafe_allow_html=True)

            except Exception as e:
                st.error(f"""
                Ocorreu um erro ao processar o arquivo.
                Verifique se o arquivo está no formato correto dos demonstrativos da ABRAMUS Internacional.

                Erro: {str(e)}
                """)

if __name__ == "__main__":
    main()
