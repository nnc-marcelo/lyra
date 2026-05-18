import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import os

# Caminho fixo para a planilha de obras
OBRAS_PATH = os.path.join("data", "obras-cadastradas-DOUGLAS-CEZAR.xlsx")

class ProcessadorRoyalties:
    def __init__(self, obras_cadastradas, autor, writer_share, nnc_writer_share,
                 editora, nnc_publisher_share, publisher_total_share, 
                 publisher_admin_share, nnc_admin_share):
        """
        Inicializa o processador com a base de obras cadastradas e parâmetros
        """
        self.obras_cadastradas = obras_cadastradas
        
        # Writer shares
        self.autor = autor
        self.writer_share = writer_share
        self.nnc_writer_share = nnc_writer_share
        
        # Publisher shares
        self.editora = editora
        self.nnc_publisher_share = nnc_publisher_share
        self.publisher_total_share = publisher_total_share
        self.publisher_admin_share = publisher_admin_share
        self.nnc_admin_share = nnc_admin_share
        self.publisher_share = publisher_total_share * publisher_admin_share
        self.admin_fee = publisher_total_share * nnc_admin_share

        # Validação dos percentuais
        total_share = (self.writer_share + self.nnc_writer_share + 
                      self.nnc_publisher_share + self.publisher_share + 
                      self.admin_fee)
        
        if not np.isclose(total_share, 1.0, rtol=1e-5):
            st.error(f"Os percentuais devem somar 100%. Soma atual: {total_share * 100:.2f}%")

    def verificar_obras(self, relatorio):
        """
        Verifica detalhes das obras e retorna obras controladas e não controladas
        """
        obras_controladas = relatorio[relatorio['CÓD. OBRA'].isin(self.obras_cadastradas['CÓD. OBRA'])]
        obras_nao_controladas = relatorio[~relatorio['CÓD. OBRA'].isin(self.obras_cadastradas['CÓD. OBRA'])]
        
        return obras_controladas, obras_nao_controladas

    def calcular_rateios(self, obras_controladas):
        valores_por_obra = obras_controladas.groupby('CÓD. OBRA')['RATEIO'].sum().reset_index()
        
        resultados = []
        for _, obra in valores_por_obra.iterrows():
            valor_total = obra['RATEIO']
            titulo = obras_controladas.loc[obras_controladas['CÓD. OBRA'] == obra['CÓD. OBRA'], 'TÍTULO DA MUSICA'].iloc[0]
            
            # Cálculos
            resultados.extend([
                {
                    'cod_obra': obra['CÓD. OBRA'],
                    'titulo': titulo,
                    'titular': f'{self.autor} (Writer)',
                    'percentual': self.writer_share * 100,
                    'valor_calculado': valor_total * self.writer_share
                },
                {
                    'cod_obra': obra['CÓD. OBRA'],
                    'titulo': titulo,
                    'titular': 'NNC (Writer)',
                    'percentual': self.nnc_writer_share * 100,
                    'valor_calculado': valor_total * self.nnc_writer_share
                },
                {
                    'cod_obra': obra['CÓD. OBRA'],
                    'titulo': titulo,
                    'titular': 'NNC (Publisher)',
                    'percentual': self.nnc_publisher_share * 100,
                    'valor_calculado': valor_total * self.nnc_publisher_share
                },
                {
                    'cod_obra': obra['CÓD. OBRA'],
                    'titulo': titulo,
                    'titular': f'{self.editora} (Publisher)',
                    'percentual': self.publisher_share * 100,
                    'valor_calculado': valor_total * self.publisher_share
                },
                {
                    'cod_obra': obra['CÓD. OBRA'],
                    'titulo': titulo,
                    'titular': 'Fee',
                    'percentual': self.admin_fee * 100,
                    'valor_calculado': valor_total * self.admin_fee
                }
            ])
        
        return pd.DataFrame(resultados)

    def processar_relatorio(self, relatorio):
        """
        Processa o relatório completo
        """
        obras_controladas, obras_nao_controladas = self.verificar_obras(relatorio)
        resultados = self.calcular_rateios(obras_controladas)
        
        # DataFrame de titulares
        df_titulares = pd.DataFrame({
            'TITULAR': [
                f'{self.autor} (Writer)',
                'NNC (Writer)',
                'NNC (Publisher)',
                f'{self.editora} (Publisher)',
                'Fee'
            ],
            'PERCENTUAL': [
                f"{self.writer_share*100:.1f}%",
                f"{self.nnc_writer_share*100:.1f}%",
                f"{self.nnc_publisher_share*100:.1f}%",
                f"{self.publisher_share*100:.1f}%",
                f"{self.admin_fee*100:.1f}%"
            ],
            'TOTAL CALCULADO': [
                resultados[resultados['titular'] == f'{self.autor} (Writer)']['valor_calculado'].sum(),
                resultados[resultados['titular'] == 'NNC (Writer)']['valor_calculado'].sum(),
                resultados[resultados['titular'] == 'NNC (Publisher)']['valor_calculado'].sum(),
                resultados[resultados['titular'] == f'{self.editora} (Publisher)']['valor_calculado'].sum(),
                resultados[resultados['titular'] == 'Fee']['valor_calculado'].sum()
            ]
        })
        
        df_titulares.loc[len(df_titulares)] = ['TOTAL', '100.0%', df_titulares['TOTAL CALCULADO'].sum()]
        
        # DataFrame de obras
        df_obras_controladas = pd.DataFrame({
            'CÓD. OBRA': obras_controladas['CÓD. OBRA'].unique(),
            'TÍTULO DA MUSICA': obras_controladas.groupby('CÓD. OBRA')['TÍTULO DA MUSICA'].first(),
            'CONTROLLED': 'Y',
            'TOTAL': obras_controladas.groupby('CÓD. OBRA')['RATEIO'].sum()
        })
        
        df_obras_nao_controladas = pd.DataFrame({
            'CÓD. OBRA': obras_nao_controladas['CÓD. OBRA'].unique(),
            'TÍTULO DA MUSICA': obras_nao_controladas.groupby('CÓD. OBRA')['TÍTULO DA MUSICA'].first(),
            'CONTROLLED': 'N',
            'TOTAL': obras_nao_controladas.groupby('CÓD. OBRA')['RATEIO'].sum()
        })
        
        df_obras = pd.concat([df_obras_controladas, df_obras_nao_controladas], ignore_index=True)
        
        return df_titulares, df_obras, resultados

def format_currency(value):
    """
    Formata valor para moeda brasileira
    """
    try:
        if isinstance(value, str):
            # Remove R$ e converte para float
            value = float(value.replace('R$', '').replace('.', '').replace(',', '.').strip())
        return f"R$ {value:,.2f}"
    except:
        return value

def carregar_obras():
    """
    Carrega a planilha de obras do caminho fixo
    """
    try:
        obras_cadastradas = pd.read_excel(OBRAS_PATH)
        return obras_cadastradas
    except Exception as e:
        st.error(f"Erro ao carregar planilha de obras: {str(e)}")
        st.error(f"Verifique se o arquivo existe em: {OBRAS_PATH}")
        return None

def main():
    st.title("EP Advance Calculator")
    
    # Carrega a planilha de obras no início
    obras_cadastradas = carregar_obras()
    if obras_cadastradas is None:
        st.stop()
    
    # Configurações em um expander no topo
    with st.expander("⚙️ Configurações", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Writer Shares")
            autor = st.text_input("Nome do Autor", "Douglas Cezar")
            writer_share = st.number_input(
                "Writer Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=37.5
            ) / 100
            nnc_writer_share = st.number_input(
                "NNC Writer Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=37.5
            ) / 100
        
        with col2:
            st.subheader("Publisher Shares")
            editora = st.text_input("Nome da Editora", "DC Editora")
            publisher_total_share = st.number_input(
                "Publisher Total Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=12.5
            ) / 100
            nnc_publisher_share = st.number_input(
                "NNC Publisher Share (%)",
                min_value=0.0,
                max_value=100.0,
                value=12.5
            ) / 100
            publisher_admin_share = st.number_input(
                "Publisher Admin Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=40.0
            ) / 100
            nnc_admin_share = st.number_input(
                "NNC Admin Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=60.0
            ) / 100
    
    # Upload apenas do relatório de royalties
    relatorio_file = st.file_uploader("Upload do Relatório de Royalties", type=['csv'])
    
    if relatorio_file is not None:
        try:
            # Carrega o relatório com tratamento especial para números
            relatorio = pd.read_csv(
                relatorio_file,
                sep=';',
                encoding="ISO-8859-1",
                decimal=',',
                thousands='.',
                header=4
            )
            
                     
            # Calcula o total geral (todas as obras)
            total_geral = relatorio['RATEIO'].sum()
                     
            # Processa os dados
            processador = ProcessadorRoyalties(
                obras_cadastradas,
                autor=autor,
                writer_share=writer_share,
                nnc_writer_share=nnc_writer_share,
                editora=editora,
                nnc_publisher_share=nnc_publisher_share,
                publisher_total_share=publisher_total_share,
                publisher_admin_share=publisher_admin_share,
                nnc_admin_share=nnc_admin_share
            )
            
            df_titulares, df_obras, resultados = processador.processar_relatorio(relatorio)
            
            # Calcula totais para obras controladas e não controladas
            total_controladas = df_obras[df_obras['CONTROLLED'] == 'Y']['TOTAL'].sum()
            total_nao_controladas = df_obras[df_obras['CONTROLLED'] == 'N']['TOTAL'].sum()
            
            st.write(
                "**Total Geral**", 
                format_currency(total_geral)
            )
            
            st.write(
                "**Total Obras Controladas**", 
                format_currency(total_controladas)
            )
            
            st.write(
                "**Total Obras Não Controladas**", 
                format_currency(total_nao_controladas)
            )
            
            st.write(
                "Quantidade de Obras", 
                f"{len(df_obras)} ({len(df_obras[df_obras['CONTROLLED'] == 'Y'])} controladas)"
            )
            
            # Exibe resultados
            st.header("Resumo por Titular")
            st.dataframe(
                df_titulares.style.format({
                    'TOTAL CALCULADO': format_currency
                }),
                hide_index=True
            )
            
            # Detalhamento de obras
            st.header("Detalhamento de Obras")
            
            # Adiciona filtros
            col1, col2 = st.columns([1, 3])
            with col1:
                status_filter = st.multiselect(
                    "Filtrar por Status",
                    options=['Y', 'N'],
                    default=['Y', 'N']
                )
            
            # Aplica filtros
            df_obras_filtered = df_obras[df_obras['CONTROLLED'].isin(status_filter)].copy()
            
            # Ordena por valor total
            df_obras_filtered['TOTAL_SORT'] = df_obras_filtered['TOTAL'].astype(float)
            df_obras_filtered = df_obras_filtered.sort_values('TOTAL_SORT', ascending=False)
            df_obras_filtered = df_obras_filtered.drop('TOTAL_SORT', axis=1)
            
            # Formata e exibe o DataFrame
            st.dataframe(
                df_obras_filtered.style.format({
                    'TOTAL': format_currency
                }),
                hide_index=True
            )
            
            # Download dos resultados
            st.header("Download dos Resultados")
            
            col1, col2 = st.columns(2)
            
            with col1:
                csv_titulares = df_titulares.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "Download Resumo por Titular",
                    csv_titulares,
                    "resumo_titulares.csv",
                    "text/csv",
                    key='download-titulares'
                )
            
            with col2:
                csv_obras = df_obras.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "Download Detalhamento de Obras",
                    csv_obras,
                    "detalhamento_obras.csv",
                    "text/csv",
                    key='download-obras'
                )
            
        except Exception as e:
            st.error(f"Erro ao processar os arquivos: {str(e)}")
            st.error("Detalhes do erro para debug:")
            st.error(str(e))

if __name__ == "__main__":
    main()