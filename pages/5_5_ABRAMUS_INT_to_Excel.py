import streamlit as st
import pdfplumber
import pandas as pd
import re
from datetime import datetime
import io
import base64

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

def extract_data_from_pdf(pdf_file):
    """Extrai dados do arquivo PDF"""
    data = []
    
    with pdfplumber.open(pdf_file) as pdf:
        current_title = None
        current_isrc = None
        
        for page in pdf.pages:
            text = page.extract_text()
            lines = text.split('\n')
            
            for line in lines:
                if any(x in line for x in ['DISTRIBUIÇÃO DE DIREITOS', 'DATA :', 'TOTAL:', 'DEMONSTRATIVO', 'CPF:', 'ABRAMUS:', 'ECAD:']):
                    continue
                    
                # Detecta linha de título + ISRC
                isrc_match = re.search(r'(T\d{10})', line)
                if isrc_match:
                    parts = line.split()
                    isrc_index = next(i for i, part in enumerate(parts) if re.match(r'T\d{10}', part))
                    current_title = ' '.join(parts[:isrc_index])
                    current_isrc = isrc_match.group(1)
                    continue
                
                parts = line.split()
                if len(parts) >= 6 and current_title:
                    try:
                        # Captura valor e período
                        value = float(parts[-1].replace(',', '.'))
                        period_pattern = r'\d{4}/\d{2}\s*-\s*\d{4}/\d{2}'
                        period_match = re.search(period_pattern, line)
                        if not period_match:
                            continue
                        period = period_match.group(0)
                        
                        # Posições fixas apenas para sociedade e território
                        society = parts[0]
                        territory = parts[1]
                        
                        # Captura rubrica usando tudo que está entre território e período
                        period_start_index = line.find(period)
                        rubrica_text = line[len(society) + len(territory) + 2 : period_start_index].strip()
                        
                        data.append({
                            'Título': current_title,
                            'ISRC/ISWC': current_isrc,
                            'Sociedade': society,
                            'Território': territory,
                            'Rubrica': rubrica_text,
                            'Direito': 'AUTORAL',
                            'Período': period,
                            'Rendimento': value
                        })
                    except:
                        continue
    
    return pd.DataFrame(data)

def main():
    st.title("ABRAMUS INT to Excel")
    st.caption("Processa o demonstrativo internacional da ABRAMUS em pdf e gera um relatório Excel.")
    
    uploaded_file = st.file_uploader("Faça upload do demonstrativo PDF da ABRAMUS", type="pdf")
    
    if uploaded_file is not None:
        with st.spinner('Processando o arquivo... Por favor, aguarde.'):
            try:
                df = extract_data_from_pdf(uploaded_file)
                
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