import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import os

# Caminho fixo para a planilha de obras
OBRAS_PATH = os.path.join("data", "catalogs", "douglas-cezar", "obras-cadastradas-DOUGLAS-CEZAR.xlsx")

def format_currency(value):
    """
    Formata valor para moeda brasileira
    """
    try:
        if isinstance(value, str):
            value = float(value.replace('R$', '').replace('.', '').replace(',', '.').strip())
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return value

class ProcessadorRoyalties:
    def __init__(self, obras_cadastradas, tipo_relatorio, autor, editora, 
                 writer_share=0.5, nnc_writer_share=0.5,
                 publisher_total_share=0.5, nnc_publisher_share=0.5,
                 publisher_admin_share=0.4, nnc_admin_share=0.6):
        self.obras_cadastradas = obras_cadastradas
        self.tipo_relatorio = tipo_relatorio
        self.autor = autor
        self.editora = editora
        
        if tipo_relatorio == "Writer":
            self.writer_share = writer_share
            self.nnc_writer_share = nnc_writer_share
            self.publisher_share = 0
            self.nnc_publisher_share = 0
            self.publisher_admin_share = 0
            self.nnc_admin_share = 0
        else:  # Publisher
            self.writer_share = 0
            self.nnc_writer_share = 0
            self.publisher_share = publisher_total_share
            self.nnc_publisher_share = nnc_publisher_share
            self.publisher_admin_share = publisher_admin_share
            self.nnc_admin_share = nnc_admin_share

        if tipo_relatorio == "Writer":
            total_share = self.writer_share + self.nnc_writer_share
        else:
            total_share = self.publisher_share + self.nnc_publisher_share
        
        if not np.isclose(total_share, 1.0, rtol=1e-5):
            st.error(f"Os percentuais devem somar 100%. Soma atual: {total_share * 100:.2f}%")

    def verificar_obras(self, relatorio):
        """
        Verifica e classifica as obras baseado em seu status de aquisição e controle
        """
        # Identificar obras que não estão cadastradas
        obras_relatorio = relatorio[['ISRC/ISWC', 'TITULOTITULO']].drop_duplicates()
        obras_cadastradas = set(self.obras_cadastradas['ISWC'].unique())
        obras_nao_cadastradas_df = obras_relatorio[~obras_relatorio['ISRC/ISWC'].isin(obras_cadastradas)]

        if not obras_nao_cadastradas_df.empty:
            obras_nao_cadastradas_list = obras_nao_cadastradas_df.apply(
                lambda row: f"{row['ISRC/ISWC']} - {row['TITULOTITULO']}", axis=1
            ).tolist()
            st.warning("As seguintes obras não estão cadastradas:")
            for obra_info in obras_nao_cadastradas_list:
                st.warning(obra_info)
            st.warning("Por favor, verifique e adicione-as à lista de obras cadastradas, se necessário.")

        # Filtrar o relatório para incluir apenas obras cadastradas
        relatorio_filtrado = relatorio[relatorio['ISRC/ISWC'].isin(obras_cadastradas)]

        # Realizar o merge apenas com as obras cadastradas
        obras_merge = relatorio_filtrado.merge(
            self.obras_cadastradas[['ISWC', 'AQUIRED', 'CONTROLLED']], 
            left_on='ISRC/ISWC',
            right_on='ISWC',
            how='inner'
        )

        if self.tipo_relatorio == "Writer":
            obras_acquired = obras_merge[obras_merge['AQUIRED'] == 'Y']
            obras_nao_acquired = obras_merge[obras_merge['AQUIRED'] == 'N']
            return obras_acquired, obras_nao_acquired
        else:
            obras_acquired = obras_merge[obras_merge['AQUIRED'] == 'Y']
            obras_nao_acquired = obras_merge[obras_merge['AQUIRED'] == 'N']
            
            obras_acquired_controlled = obras_acquired[obras_acquired['CONTROLLED'] == 'Y']
            obras_acquired_nao_controlled = obras_acquired[obras_acquired['CONTROLLED'] == 'N']
            obras_nao_acquired_controlled = obras_nao_acquired[obras_nao_acquired['CONTROLLED'] == 'Y']
            obras_nao_acquired_nao_controlled = obras_nao_acquired[obras_nao_acquired['CONTROLLED'] == 'N']
            
            return (obras_acquired_controlled, obras_acquired_nao_controlled, 
                    obras_nao_acquired_controlled, obras_nao_acquired_nao_controlled)

    def processar_relatorio(self, relatorio):
        """
        Processa o relatório e retorna os resultados calculados
        """
        # Agrupa as obras por ISWC e calcula o total
        df_obras = relatorio.groupby(['ISRC/ISWC', 'TITULOTITULO']).agg({
            'RATEIO': 'sum'
        }).reset_index()
        df_obras = df_obras.rename(columns={'RATEIO': 'TOTAL'})
        
        # Merge com obras cadastradas para obter status
        df_obras = df_obras.merge(
            self.obras_cadastradas[['ISWC', 'AQUIRED', 'CONTROLLED']],
            left_on='ISRC/ISWC',
            right_on='ISWC',
            how='inner'
        )

        # Inicializa lista para armazenar resultados
        resultados = []
        
        if self.tipo_relatorio == "Writer":
            # Processa obras adquiridas
            obras_acquired = df_obras[df_obras['AQUIRED'] == 'Y']
            for _, obra in obras_acquired.iterrows():
                resultados.extend([
                    {
                        'TITULAR': f'{self.autor} (Writer Share)',
                        'PERCENTUAL': self.writer_share * 100,
                        'TOTAL CALCULADO': obra['TOTAL'] * self.writer_share
                    },
                    {
                        'TITULAR': 'NNC Acquirer (Writer Share)',
                        'PERCENTUAL': self.nnc_writer_share * 100,
                        'TOTAL CALCULADO': obra['TOTAL'] * self.nnc_writer_share
                    }
                ])
            
            # Processa obras não adquiridas
            obras_nao_acquired = df_obras[df_obras['AQUIRED'] == 'N']
            for _, obra in obras_nao_acquired.iterrows():
                resultados.append({
                    'TITULAR': 'NNC (Writer)',
                    'PERCENTUAL': 100.0,
                    'TOTAL CALCULADO': obra['TOTAL']
                })
            
            # Cria DataFrame de resultados por titular
            df_titulares = pd.DataFrame(resultados)
            df_titulares = df_titulares.groupby('TITULAR').agg({
                'PERCENTUAL': 'first',
                'TOTAL CALCULADO': 'sum'
            }).reset_index()
            
            return df_titulares, df_obras, resultados
            
        else:  # Publisher
            resultados_aquisicao = []
            resultados_administracao = []
            
            # Processa obras por tipo
            for _, obra in df_obras.iterrows():
                if obra['AQUIRED'] == 'Y':
                    if obra['CONTROLLED'] == 'Y':
                        # Adiciona resultados de aquisição
                        resultados_aquisicao.extend([
                            {
                                'TITULAR': f'{self.editora} (Publisher)',
                                'PERCENTUAL': self.publisher_share * self.publisher_admin_share * 100,
                                'TOTAL CALCULADO': obra['TOTAL'] * self.publisher_share * self.publisher_admin_share
                            },
                            {
                                'TITULAR': 'NNC (Acquirer)',
                                'PERCENTUAL': self.nnc_publisher_share * 100,
                                'TOTAL CALCULADO': obra['TOTAL'] * self.nnc_publisher_share
                            },
                            {
                                'TITULAR': 'NNC (Admin)',
                                'PERCENTUAL': self.publisher_share * self.nnc_admin_share * 100,
                                'TOTAL CALCULADO': obra['TOTAL'] * self.publisher_share * self.nnc_admin_share
                            }
                        ])
                    else:
                        # Adiciona resultados de administração
                        resultados_administracao.extend([
                            {
                                'TITULAR': f'{self.editora} (Publisher)',
                                'PERCENTUAL': self.publisher_admin_share * 100,
                                'TOTAL CALCULADO': obra['TOTAL'] * self.publisher_admin_share
                            },
                            {
                                'TITULAR': 'NNC (Admin)',
                                'PERCENTUAL': self.nnc_admin_share * 100,
                                'TOTAL CALCULADO': obra['TOTAL'] * self.nnc_admin_share
                            }
                        ])
            
            # Cria DataFrames de resultados por titular
            df_titulares_aquisicao = pd.DataFrame(resultados_aquisicao)
            df_titulares_administracao = pd.DataFrame(resultados_administracao)
            
            if not df_titulares_aquisicao.empty:
                df_titulares_aquisicao = df_titulares_aquisicao.groupby('TITULAR').agg({
                    'PERCENTUAL': 'first',
                    'TOTAL CALCULADO': 'sum'
                }).reset_index()
            
            if not df_titulares_administracao.empty:
                df_titulares_administracao = df_titulares_administracao.groupby('TITULAR').agg({
                    'PERCENTUAL': 'first',
                    'TOTAL CALCULADO': 'sum'
                }).reset_index()
            
            return df_titulares_aquisicao, df_titulares_administracao, df_obras, resultados_aquisicao + resultados_administracao

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

def processar_relatorio_internacional(file):
    """
    Processa o relatório internacional no novo formato
    """
    try:
        df = pd.read_excel(file, sheet_name='Detalhamento Completo')
        
        # Renomeia apenas para os nomes internos usados no processamento
        df = df.rename(columns={
            'Rendimento': 'RATEIO',
            'Título': 'TITULOTITULO',
            'ISRC/ISWC': 'ISRC/ISWC'  # Mantém o nome original
        })
        
        # Garante que o Rendimento seja numérico
        df['RATEIO'] = pd.to_numeric(df['RATEIO'])
        
        # Remove linhas com valores nulos ou zero no rendimento
        df = df.dropna(subset=['RATEIO'])
        df = df[df['RATEIO'] != 0]
        
        return df
        
    except Exception as e:
        st.error(f"Erro ao processar relatório internacional: {str(e)}")
        st.error(f"Detalhes do erro: {str(e)}")
        return None

def main():
    st.title("EP Advance Calculator INT")
    
    # Carrega a planilha de obras no início
    obras_cadastradas = carregar_obras()
    if obras_cadastradas is None:
        st.stop()
    
    # Seletor de tipo de relatório
    tipo_relatorio = st.radio(
        "Tipo de Relatório",
        ["Writer", "Publisher"],
        horizontal=True
    )
    
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
                value=50.0 if tipo_relatorio == "Writer" else 0.0,
                disabled=tipo_relatorio != "Writer"
            ) / 100
            nnc_writer_share = st.number_input(
                "NNC Writer Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=50.0 if tipo_relatorio == "Writer" else 0.0,
                disabled=tipo_relatorio != "Writer"
            ) / 100
        
        with col2:
            st.subheader("Publisher Shares")
            editora = st.text_input("Nome da Editora", "DC Editora")
            publisher_total_share = st.number_input(
                "Publisher Total Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=50.0 if tipo_relatorio == "Publisher" else 0.0,
                disabled=tipo_relatorio != "Publisher"
            ) / 100
            nnc_publisher_share = st.number_input(
                "NNC Publisher Share (%)",
                min_value=0.0,
                max_value=100.0,
                value=50.0 if tipo_relatorio == "Publisher" else 0.0,
                disabled=tipo_relatorio != "Publisher"
            ) / 100
            publisher_admin_share = st.number_input(
                "Publisher Admin Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=40.0 if tipo_relatorio == "Publisher" else 0.0,
                disabled=tipo_relatorio != "Publisher"
            ) / 100
            nnc_admin_share = st.number_input(
                "NNC Admin Share (%)", 
                min_value=0.0, 
                max_value=100.0,
                value=60.0 if tipo_relatorio == "Publisher" else 0.0,
                disabled=tipo_relatorio != "Publisher"
            ) / 100

        # Adiciona validações dos percentuais
        if tipo_relatorio == "Writer":
            writer_total = writer_share + nnc_writer_share
            if not np.isclose(writer_total, 1.0, rtol=1e-5):
                st.error(f"Os percentuais de Writer devem somar 100%. Soma atual: {writer_total * 100:.2f}%")
        else:
            publisher_total = publisher_total_share + nnc_publisher_share
            admin_total = publisher_admin_share + nnc_admin_share
            if not np.isclose(publisher_total, 1.0, rtol=1e-5):
                st.error(f"Os percentuais de Publisher devem somar 100%. Soma atual: {publisher_total * 100:.2f}%")
            if not np.isclose(admin_total, 1.0, rtol=1e-5):
                st.error(f"Os percentuais de Admin devem somar 100%. Soma atual: {admin_total * 100:.2f}%")

    # Upload do relatório de royalties
    relatorio_file = st.file_uploader(f"Upload do Relatório de {tipo_relatorio}", type=['xlsx'])

    if relatorio_file is not None:
        try:
            # Usa a função processadora específica para relatório internacional
            relatorio = processar_relatorio_internacional(relatorio_file)
            if relatorio is None:
                st.stop()

            # Processa os dados
            processador = ProcessadorRoyalties(
                obras_cadastradas,
                tipo_relatorio=tipo_relatorio,
                autor=autor,
                editora=editora,
                writer_share=writer_share,
                nnc_writer_share=nnc_writer_share,
                publisher_total_share=publisher_total_share,
                nnc_publisher_share=nnc_publisher_share,
                publisher_admin_share=publisher_admin_share,
                nnc_admin_share=nnc_admin_share
            )

            # Processa o relatório e obtém os resultados
            if tipo_relatorio == "Writer":
                df_titulares, df_obras, resultados = processador.processar_relatorio(relatorio)
            else:
                df_titulares_aquisicao, df_titulares_administracao, df_obras, resultados = processador.processar_relatorio(relatorio)

            # Calcula totais
            total_geral = relatorio['RATEIO'].sum()
            total_acquired = df_obras[df_obras['AQUIRED'] == 'Y']['TOTAL'].sum()
            total_nao_acquired = df_obras[df_obras['AQUIRED'] == 'N']['TOTAL'].sum()
            total_processado = df_obras['TOTAL'].sum()
            total_nao_processado = total_geral - total_processado

            # Exibe totais
            st.write(f"**TOTAL GERAL: {format_currency(total_geral)}**")
            st.write("**Total Processado:**", format_currency(total_processado))
            if total_nao_processado > 0:
                st.write(f":red[**Total Não Processado (obras não cadastradas): {format_currency(total_nao_processado)}**]")
            st.write("**Total Obras Adquiridas:**", format_currency(total_acquired))
            st.write(f":red[**Total Obras Não Adquiridas: {format_currency(total_nao_acquired)}**]")

            st.divider()

            # Informações sobre quantidade de obras
            obras_nao_cadastradas = set(relatorio['ISRC/ISWC'].unique()) - set(obras_cadastradas['ISWC'].unique())
            st.write("Quantidade de Obras Processadas:", 
                    f"{len(df_obras)} ({len(df_obras[df_obras['AQUIRED'] == 'Y'])} adquiridas)")
            st.write("Quantidade de Obras Não Processadas (não cadastradas):", 
                    f"{len(obras_nao_cadastradas)}")

            st.divider()

            # Exibe resumos por titular
            if tipo_relatorio == "Writer":
                st.header("Resumo por Titular (Writer)")
                # Formatação do campo PERCENTUAL
                df_titulares['PERCENTUAL'] = df_titulares['PERCENTUAL'].apply(lambda x: f"{x:.1f}%")
                st.dataframe(
                    df_titulares.style.format({
                        'TOTAL CALCULADO': format_currency
                    }),
                    hide_index=True
                )
            else:
                st.header("Resumo por Titular (Publisher) - Aquisição")
                # Formatação do campo PERCENTUAL para aquisição
                df_titulares_aquisicao['PERCENTUAL'] = df_titulares_aquisicao['PERCENTUAL'].apply(lambda x: f"{x:.1f}%")
                                               
                               
                st.dataframe(
                    df_titulares_aquisicao.style.format({
                        'TOTAL CALCULADO': format_currency
                    }),
                    hide_index=True
                )

            # Área de cálculos           
            st.write("Área de Cálculos")
            if 'calc_df' not in st.session_state:
                st.session_state.calc_df = pd.DataFrame(
                    columns=['Descrição', 'Valor'],
                    data=[['', 0.00] for _ in range(3)]  # Inicializa com 3 linhas vazias
                )

            edited_df = st.data_editor(
                st.session_state.calc_df,
                column_config={
                    "Descrição": st.column_config.TextColumn(
                        "Descrição",
                        width="medium",
                    ),
                    "Valor": st.column_config.NumberColumn(
                        "Valor",
                        format="R$ %.2f",
                        width="small",
                    ),
                },
                num_rows="dynamic",
                key="calc_table"
            )

            # Atualiza o DataFrame na session_state
            st.session_state.calc_df = edited_df

            if len(edited_df) > 0:
                total = edited_df['Valor'].sum()
                st.markdown(f"**Total:** {format_currency(total)}")

            # Detalhamento de obras
            st.header("Detalhamento de Obras")

            if tipo_relatorio == "Writer":
                status_filter = st.multiselect(
                    "Filtrar por Status",
                    options=['Y', 'N'],
                    default=['Y', 'N'],
                    format_func=lambda x: "Adquirida" if x == 'Y' else "Não Adquirida",
                    key="writer_filter"
                )
                
                df_obras_filtered = df_obras[df_obras['AQUIRED'].isin(status_filter)].copy()
            else:
                status_filter = st.multiselect(
                    "Filtrar por Status",
                    options=['Adquirida', 'Não Adquirida'],
                    default=['Adquirida', 'Não Adquirida'],
                    key="publisher_filter"
                )
                
                acquired_mask = (df_obras['AQUIRED'] == 'Y') if 'Adquirida' in status_filter else False
                not_acquired_mask = (df_obras['AQUIRED'] == 'N') if 'Não Adquirida' in status_filter else False
                
                df_obras_filtered = df_obras[acquired_mask | not_acquired_mask].copy()

            # Ordena por valor total
            df_obras_filtered['TOTAL_SORT'] = df_obras_filtered['TOTAL'].astype(float)
            df_obras_filtered = df_obras_filtered.sort_values('TOTAL_SORT', ascending=False)
            df_obras_filtered = df_obras_filtered.drop('TOTAL_SORT', axis=1)

            # Exibe o DataFrame
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
                if tipo_relatorio == "Writer":
                    csv_titulares = df_titulares.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        f"Download Resumo por Titular ({tipo_relatorio})",
                        csv_titulares,
                        f"resumo_titulares_{tipo_relatorio.lower()}.csv",
                        "text/csv",
                        key='download-titulares'
                    )
                else:
                    csv_titulares_aquisicao = df_titulares_aquisicao.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "Download Resumo por Titular (Aquisição)",
                        csv_titulares_aquisicao,
                        "resumo_titulares_aquisicao.csv",
                        "text/csv",
                        key='download-titulares-aquisicao'
                    )
                    csv_titulares_administracao = df_titulares_administracao.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "Download Resumo por Titular (Administração)",
                        csv_titulares_administracao,
                        "resumo_titulares_administracao.csv",
                        "text/csv",
                        key='download-titulares-administracao'
                    )
            
            with col2:
                csv_obras = df_obras.to_csv(index=False).encode('utf-8')
                st.download_button(
                    f"Download Detalhamento de Obras ({tipo_relatorio})",
                    csv_obras,
                    f"detalhamento_obras_{tipo_relatorio.lower()}.csv",
                    "text/csv",
                    key='download-obras'
                )
            
        except Exception as e:
            st.error(f"Erro ao processar os arquivos: {str(e)}")
            st.error("Detalhes do erro para debug:")
            st.error(str(e))

if __name__ == "__main__":
    main()