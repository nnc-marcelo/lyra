import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import os

# Caminho fixo para a planilha de obras
#OBRAS_PATH = os.path.join("data", "obras-cadastradas-DOUGLAS-CEZAR_v2.xlsx")
EDITORAS_DISPONIVEIS = [
    'Selecione uma editora',  # Opção padrão
    'DC Editora',
    
    # Adicione mais editoras conforme necessário
]

SHARES_POR_EDITORA = {
    # Adicione mais editoras conforme necessário
    'Selecione uma editora': {
        'publisher_total': 50.0,
        'nnc_publisher': 50.0,
        'publisher_admin': 50.0,
        'nnc_admin': 50.0
    },

    'DC Editora': {
        'publisher_total': 50.0,
        'nnc_publisher': 50.0,
        'publisher_admin': 40.0,
        'nnc_admin': 60.0
    }
   
}

@st.cache_data
def listar_artistas():
    """
    Lista todos os artistas disponíveis no diretório catalogs
    """
    catalogs_path = os.path.join("data", "catalogs")
    try:
        # Lista apenas os diretórios dentro de catalogs
        artistas = [d for d in os.listdir(catalogs_path) 
                   if os.path.isdir(os.path.join(catalogs_path, d))]
        return sorted(artistas)
    except Exception as e:
        st.error(f"Erro ao listar artistas: {str(e)}")
        return []


def encontrar_arquivo_obras(artista):
    """
    Encontra o arquivo de obras mais recente para o artista selecionado
    """
    pasta_artista = os.path.join("data", "catalogs", artista)
    try:
        # Lista todos os arquivos xlsx na pasta do artista
        arquivos = [f for f in os.listdir(pasta_artista) 
                   if f.endswith('.xlsx') and 'obras-cadastradas' in f.lower()]
        if not arquivos:
            return None
        # Retorna o caminho completo do arquivo mais recente
        arquivo_mais_recente = max(arquivos)
        return os.path.join(pasta_artista, arquivo_mais_recente)
    except Exception as e:
        st.error(f"Erro ao buscar arquivo de obras para {artista}: {str(e)}")
        return None


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

def reset_calc_area():
    """
    Reseta a área de cálculos para o estado inicial com tipos de dados explícitos
    """
    st.session_state.calc_df = pd.DataFrame({
        'Descrição': [''] * 4,
        'Valor': [0.00] * 4
    }).astype({
        'Descrição': 'string',
        'Valor': 'float64'
    })


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
        obras_relatorio = relatorio[['CÓD. OBRA', 'TÍTULO DA MUSICA']].drop_duplicates()
        obras_cadastradas = set(self.obras_cadastradas['CÓD. OBRA'].unique())
        obras_nao_cadastradas_df = obras_relatorio[~obras_relatorio['CÓD. OBRA'].isin(obras_cadastradas)]

        if not obras_nao_cadastradas_df.empty:
            obras_nao_cadastradas_list = obras_nao_cadastradas_df.apply(
                lambda row: f"{row['CÓD. OBRA']} - {row['TÍTULO DA MUSICA']}", axis=1
            ).tolist()
            st.warning("As seguintes obras não estão cadastradas:")
            for obra_info in obras_nao_cadastradas_list:
                st.warning(obra_info)
            st.warning("Por favor, verifique e adicione-as à lista de obras cadastradas, se necessário.")

        # Filtrar o relatório para incluir apenas obras cadastradas
        relatorio_filtrado = relatorio[relatorio['CÓD. OBRA'].isin(obras_cadastradas)]

        # Realizar o merge apenas com as obras cadastradas
        obras_merge = relatorio_filtrado.merge(
            self.obras_cadastradas[['CÓD. OBRA', 'AQUIRED', 'CONTROLLED']], 
            on='CÓD. OBRA', 
            how='inner'
        )

        if self.tipo_relatorio == "Writer":
            obras_acquired = obras_merge[obras_merge['AQUIRED'] == 'Y']
            obras_nao_acquired = obras_merge[obras_merge['AQUIRED'] == 'N']
            return obras_acquired, obras_nao_acquired
        else:
            # Para Publisher, primeiro separamos por AQUIRED
            obras_acquired = obras_merge[obras_merge['AQUIRED'] == 'Y']
            obras_nao_acquired = obras_merge[obras_merge['AQUIRED'] == 'N']
            
            # Depois separamos cada grupo por CONTROLLED
            obras_acquired_controlled = obras_acquired[obras_acquired['CONTROLLED'] == 'Y']
            obras_acquired_nao_controlled = obras_acquired[obras_acquired['CONTROLLED'] == 'N']
            obras_nao_acquired_controlled = obras_nao_acquired[obras_nao_acquired['CONTROLLED'] == 'Y']
            obras_nao_acquired_nao_controlled = obras_nao_acquired[obras_nao_acquired['CONTROLLED'] == 'N']
            
            return (obras_acquired_controlled, obras_acquired_nao_controlled, 
                    obras_nao_acquired_controlled, obras_nao_acquired_nao_controlled)

    def calcular_rateios_publisher_aquisicao(self, obra, valor_total, titulo):
        """
        Calcula os rateios para obras adquiridas no modelo de aquisição
        """
        resultados = []
        
        # Distribuição padrão para obras adquiridas
        publisher_valor = valor_total * self.publisher_share * self.publisher_admin_share
        nnc_publisher_valor = valor_total * self.nnc_publisher_share
        admin_fee_valor = valor_total * self.publisher_share * self.nnc_admin_share
        
        resultados.extend([
            {
                'cod_obra': obra,
                'titulo': titulo,
                'titular': f'{self.editora} (Publisher)',
                'percentual': self.publisher_share * self.publisher_admin_share * 100,
                'valor_calculado': publisher_valor,
                'tipo': 'aquisicao'
            },
            {
                'cod_obra': obra,
                'titulo': titulo,
                'titular': 'NNC (Acquirer)',
                'percentual': self.nnc_publisher_share * 100,
                'valor_calculado': nnc_publisher_valor,
                'tipo': 'aquisicao'
            },
            {
                'cod_obra': obra,
                'titulo': titulo,
                'titular': 'NNC (Admin)',
                'percentual': self.publisher_share * self.nnc_admin_share * 100,
                'valor_calculado': admin_fee_valor,
                'tipo': 'aquisicao'
            }
        ])
        
        return resultados
    
    def calcular_rateios_publisher_administracao(self, obra, valor_total, titulo):
        resultados = []

        # Ajuste para considerar apenas DC Editora e NNC (Admin)
        publisher_valor = valor_total * self.publisher_admin_share
        nnc_admin_valor = valor_total * self.nnc_admin_share

        resultados.extend([
            {
                'cod_obra': obra,
                'titulo': titulo,
                'titular': f'{self.editora} (Publisher)',
                'percentual': self.publisher_admin_share * 100,
                'valor_calculado': publisher_valor,
                'tipo': 'administracao'
            },
            {
                'cod_obra': obra,
                'titulo': titulo,
                'titular': 'NNC (Admin)',
                'percentual': self.nnc_admin_share * 100,
                'valor_calculado': nnc_admin_valor,
                'tipo': 'administracao'
            }
        ])

        return resultados


    def calcular_rateios(self, obras_acquired, obras_nao_acquired=None):
        resultados = []
    
        if self.tipo_relatorio == "Writer":
            # Processamento de obras adquiridas - divisão 50/50
            for cod_obra, obra in obras_acquired.groupby('CÓD. OBRA'):
                valor_total = obra['RATEIO'].sum()
                titulo = obra['TÍTULO DA MUSICA'].iloc[0]
                
                # Aplica os percentuais no valor total da obra adquirida
                resultados.extend([
                    {
                        'cod_obra': cod_obra,
                        'titulo': titulo,
                        'titular': f'{self.autor} (Writer)',
                        'percentual': self.writer_share * 100,
                        'valor_calculado': valor_total * self.writer_share,
                        'status': 'acquired'
                    },
                    {
                        'cod_obra': cod_obra,
                        'titulo': titulo,
                        'titular': 'NNC (Writer)',
                        'percentual': self.nnc_writer_share * 100,
                        'valor_calculado': valor_total * self.nnc_writer_share,
                        'status': 'acquired'
                    }
                ])
                
            # Obras não adquiridas - 100% para NNC
            if obras_nao_acquired is not None:
                for cod_obra, obra in obras_nao_acquired.groupby('CÓD. OBRA'):
                    valor_total = obra['RATEIO'].sum()
                    titulo = obra['TÍTULO DA MUSICA'].iloc[0]
                    
                    resultados.append({
                        'cod_obra': cod_obra,
                        'titulo': titulo,
                        'titular': 'NNC (Writer)',
                        'percentual': 100.0,
                        'valor_calculado': valor_total,
                        'status': 'not_acquired'
                    })
                    
            return pd.DataFrame(resultados)
                
        else:
            # Código para Publisher
            pass  # Implementação para Publisher

        return pd.DataFrame(resultados)

    def processar_relatorio(self, relatorio):
        if self.tipo_relatorio == "Writer":
            obras_acquired, obras_nao_acquired = self.verificar_obras(relatorio)
            resultados_df = self.calcular_rateios(obras_acquired, obras_nao_acquired)
            
            # Cria resumo por titular
            df_titulares = self._criar_resumo_titulares(resultados_df)
            
            # Cria DataFrame de obras
            df_obras = pd.concat([obras_acquired, obras_nao_acquired], ignore_index=True)
            df_obras = df_obras[['CÓD. OBRA', 'TÍTULO DA MUSICA', 'AQUIRED', 'CONTROLLED', 'RATEIO']]
            df_obras.rename(columns={'RATEIO': 'TOTAL'}, inplace=True)
            df_obras = df_obras.groupby(['CÓD. OBRA', 'TÍTULO DA MUSICA', 'AQUIRED', 'CONTROLLED']).sum().reset_index()
            
            return df_titulares, df_obras, resultados_df
                
        else:  # Publisher
            (obras_acquired_controlled,
             obras_acquired_nao_controlled,
             obras_nao_acquired_controlled,
             obras_nao_acquired_nao_controlled) = self.verificar_obras(relatorio)
        
            resultados = []
            
            # Processa obras adquiridas (modelo de aquisição)
            for _, obra in pd.concat([obras_acquired_controlled, obras_acquired_nao_controlled]).groupby('CÓD. OBRA'):
                valor_total = obra['RATEIO'].sum()
                titulo = obra['TÍTULO DA MUSICA'].iloc[0]
                resultados.extend(self.calcular_rateios_publisher_aquisicao(
                    obra['CÓD. OBRA'].iloc[0], 
                    valor_total,
                    titulo
                ))
            
            # Processa obras não adquiridas (modelo de administração)
            for _, obra in pd.concat([obras_nao_acquired_controlled, obras_nao_acquired_nao_controlled]).groupby('CÓD. OBRA'):
                valor_total = obra['RATEIO'].sum()
                titulo = obra['TÍTULO DA MUSICA'].iloc[0]
                resultados.extend(self.calcular_rateios_publisher_administracao(
                    obra['CÓD. OBRA'].iloc[0],
                    valor_total,
                    titulo
                ))
            
            resultados_df = pd.DataFrame(resultados)
            
            # Cria dois DataFrames de resumo separados
            df_titulares_aquisicao = self._criar_resumo_titulares(
                resultados_df[resultados_df['tipo'] == 'aquisicao']
            )
            
            df_titulares_administracao = self._criar_resumo_titulares(
                resultados_df[resultados_df['tipo'] == 'administracao']
            )
            
            # Cria DataFrame de obras
            df_obras = pd.concat([
                obras_acquired_controlled,
                obras_acquired_nao_controlled,
                obras_nao_acquired_controlled,
                obras_nao_acquired_nao_controlled
            ], ignore_index=True)
            df_obras = df_obras[['CÓD. OBRA', 'TÍTULO DA MUSICA', 'AQUIRED', 'CONTROLLED', 'RATEIO']]
            df_obras.rename(columns={'RATEIO': 'TOTAL'}, inplace=True)
            df_obras = df_obras.groupby(['CÓD. OBRA', 'TÍTULO DA MUSICA', 'AQUIRED', 'CONTROLLED']).sum().reset_index()
            
            return df_titulares_aquisicao, df_titulares_administracao, df_obras, resultados_df
        
    def _criar_resumo_titulares(self, resultados):
        """
        Cria resumo por titular a partir dos resultados
        """
        if resultados.empty:
            return pd.DataFrame(columns=['TITULAR', 'PERCENTUAL', 'TOTAL CALCULADO'])
        
        if self.tipo_relatorio == "Writer":
            resultados_acquired = resultados[resultados['status'] == 'acquired']
            resultados_not_acquired = resultados[resultados['status'] == 'not_acquired']
            
            total_acquired = resultados_acquired['valor_calculado'].sum() if not resultados_acquired.empty else 0
            total_not_acquired = resultados_not_acquired['valor_calculado'].sum() if not resultados_not_acquired.empty else 0
            
            linhas = []
            
            # Calcula o valor para o autor (apenas das obras adquiridas)
            if total_acquired > 0:
                autor_total = total_acquired * self.writer_share
                linhas.append({
                    'TITULAR': f'{self.autor} (Writer Share)',
                    'PERCENTUAL': f"{self.writer_share * 100:.1f}%",
                    'TOTAL CALCULADO': autor_total
                })
            else:
                autor_total = 0
                linhas.append({
                    'TITULAR': f'{self.autor} (Writer)',
                    'PERCENTUAL': '0.0%',
                    'TOTAL CALCULADO': autor_total
                })
            
            # Calcula o valor para NNC (apenas das obras adquiridas)
            nnc_acquired_total = total_acquired * self.nnc_writer_share
            linhas.append({
                'TITULAR': 'NNC Acquirer (Writer Share)',
                'PERCENTUAL': f"{self.nnc_writer_share * 100:.1f}%",
                'TOTAL CALCULADO': nnc_acquired_total
            })
            
                      
            # Calcula o total geral para NNC (acquired + not acquired)
            nnc_total = nnc_acquired_total + total_not_acquired
            total_geral = autor_total + nnc_acquired_total
            
            # Adiciona linha de total
            linhas.append({
                'TITULAR': 'TOTAL',
                'PERCENTUAL': '100.0%',
                'TOTAL CALCULADO': total_geral
            })
            
            return pd.DataFrame(linhas)
           

        else:
            # Implementação para Publisher
            df_titulares = resultados.groupby('titular').agg({
                'percentual': 'first',
                'valor_calculado': 'sum'
            }).reset_index()
            df_titulares.rename(columns={
                'titular': 'TITULAR',
                'percentual': 'PERCENTUAL',
                'valor_calculado': 'TOTAL CALCULADO'
            }, inplace=True)
            
            # Formatação do campo PERCENTUAL
            df_titulares['PERCENTUAL'] = df_titulares['PERCENTUAL'].apply(lambda x: f"{x:.1f}%")
            
            # Adiciona linha de total
            total_geral = df_titulares['TOTAL CALCULADO'].sum()
            total_row = pd.DataFrame({
                'TITULAR': ['TOTAL'],
                'PERCENTUAL': [''],
                'TOTAL CALCULADO': [total_geral]
            })
            df_titulares = pd.concat([df_titulares, total_row], ignore_index=True)
            
            return df_titulares            



def carregar_obras(artista):
    """
    Carrega a planilha de obras do artista selecionado
    """
    caminho_arquivo = encontrar_arquivo_obras(artista)
    if not caminho_arquivo:
        st.error(f"Nenhum arquivo de obras encontrado para {artista}")
        return None
    
    try:
        obras_cadastradas = pd.read_excel(caminho_arquivo)
        return obras_cadastradas
    except Exception as e:
        st.error(f"Erro ao carregar planilha de obras: {str(e)}")
        st.error(f"Verifique se o arquivo existe em: {caminho_arquivo}")
        return None
    
def main():
    st.title("EP Advance Calculator")
    
    # Seletor de artista
    artistas = listar_artistas()
    if not artistas:
        st.error("Nenhum artista encontrado no diretório de catálogos")
        st.stop()
    
    artista_selecionado = st.selectbox(
        "Selecione o Artista",
        artistas,
        format_func=lambda x: x.replace('-', ' ').title()
    )
    
    # Carrega a planilha de obras do artista selecionado
    obras_cadastradas = carregar_obras(artista_selecionado)
    if obras_cadastradas is None:
        st.stop()
    
    # Seletor de tipo de relatório - MOVIDO PARA ANTES DAS CONFIGURAÇÕES
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
            autor = st.text_input(
                "Nome do Autor", 
                value=artista_selecionado.replace('-', ' ').title(),  # Formata o nome do artista selecionado
                key="autor_nome"
            )
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
        
            # Seletor de editora
            editora = st.selectbox(
                "Nome da Editora",
                options=EDITORAS_DISPONIVEIS,
                key="editora_nome"
            )
            
            # Obtém os percentuais padrão para a editora selecionada
            shares_padrao = SHARES_POR_EDITORA.get(editora, SHARES_POR_EDITORA['Selecione uma editora'])
            
            # Checkbox para habilitar edição manual
            ajuste_manual = st.checkbox("Permitir ajuste manual dos percentuais", 
                                    value=False, 
                                    key="ajuste_manual")
            
            # Campos desabilitados se nenhuma editora selecionada ou não é tipo Publisher
            campos_desabilitados = (editora == 'Selecione uma editora') or (tipo_relatorio != "Publisher")
            
            # Publisher Total Share
            publisher_total_share = st.number_input(
                "Publisher Total Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=shares_padrao['publisher_total'],
                disabled=campos_desabilitados or not ajuste_manual
            ) / 100
            
            # NNC Publisher Share
            nnc_publisher_share = st.number_input(
                "NNC Publisher Share (%)",
                min_value=0.0,
                max_value=100.0,
                value=shares_padrao['nnc_publisher'],
                disabled=campos_desabilitados or not ajuste_manual
            ) / 100
            
            # Publisher Admin Share
            publisher_admin_share = st.number_input(
                "Publisher Admin Share (%)", 
                min_value=0.0, 
                max_value=100.0, 
                value=shares_padrao['publisher_admin'],
                disabled=campos_desabilitados or not ajuste_manual
            ) / 100
            
            # NNC Admin Share
            nnc_admin_share = st.number_input(
                "NNC Admin Share (%)", 
                min_value=0.0, 
                max_value=100.0,
                value=shares_padrao['nnc_admin'],
                disabled=campos_desabilitados or not ajuste_manual
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
    relatorio_file = st.file_uploader(f"Upload do Relatório de {tipo_relatorio}", type=['csv'])

    # Verifica se é um novo arquivo
    if relatorio_file is not None:
        current_file = relatorio_file.name
        if 'last_file' in st.session_state and st.session_state.last_file != current_file:
            reset_calc_area()
        st.session_state.last_file = current_file


    if relatorio_file is not None:
        try:
            # Carrega o relatório
            relatorio = pd.read_csv(
                relatorio_file,
                sep=';',
                encoding="ISO-8859-1",
                decimal=',',
                thousands='.',
                header=4
            )
            
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
            
            total_geral = relatorio['RATEIO'].sum()
            obras_nao_cadastradas = set(relatorio['CÓD. OBRA'].unique()) - set(obras_cadastradas['CÓD. OBRA'].unique())

            if tipo_relatorio == "Writer":
                # Processamento Writer
                df_titulares, df_obras, resultados = processador.processar_relatorio(relatorio)
                total_acquired = df_obras[df_obras['AQUIRED'] == 'Y']['TOTAL'].sum()
                total_nao_acquired = df_obras[df_obras['AQUIRED'] == 'N']['TOTAL'].sum()
                total_processado = df_obras['TOTAL'].sum()
                total_nao_processado = total_geral - total_processado
                
                st.write(f"**TOTAL GERAL: {format_currency(total_geral)}**")
                st.write("**Total Processado:**", format_currency(total_processado))
                if total_nao_processado > 0:
                    st.write(f":red[**Total Não Processado (obras não cadastradas): {format_currency(total_nao_processado)}**]")
                st.write("**Total Obras Adquiridas:**", format_currency(total_acquired))
                st.write(f":red[**Total Obras Não Adquiridas: {format_currency(total_nao_acquired)}**]")
                
                st.divider()
                
                st.write("Quantidade de Obras Processadas:", 
                    f"{len(df_obras)} ({len(df_obras[df_obras['AQUIRED'] == 'Y'])} adquiridas)")
                st.write("Quantidade de Obras Não Processadas (não cadastradas):", 
                    f"{len(obras_nao_cadastradas)}")
                
                st.divider()

                # Exibe resumo por titular
                st.header("Resumo por Titular (Writer)")
                st.dataframe(
                    df_titulares.style.format({
                        'TOTAL CALCULADO': format_currency
                    }),
                    hide_index=True
                )
                
            else:  # Publisher
                # Processamento Publisher
                df_titulares_aquisicao, df_titulares_administracao, df_obras, resultados = processador.processar_relatorio(relatorio)
    
                # Calcula totais
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

                st.write("Quantidade de Obras Processadas:", 
                    f"{len(df_obras)} ({len(df_obras[df_obras['AQUIRED'] == 'Y'])} adquiridas)")
                st.write("Quantidade de Obras Não Processadas (não cadastradas):", 
                    f"{len(obras_nao_cadastradas)}")
                
                st.divider()
                
                # Exibe os dois resumos
                st.header("Resumo por Titular (Publisher) - Aquisição")
                st.dataframe(
                    df_titulares_aquisicao.style.format({
                        'TOTAL CALCULADO': format_currency
                    }),
                    hide_index=True
                )
                
                st.header("Resumo por Titular (Publisher) - Administração")
                st.dataframe(
                    df_titulares_administracao.style.format({
                        'TOTAL CALCULADO': format_currency
                    }),
                    hide_index=True
                )

            # Área de cálculos           
            st.write("Área de Cálculos")
            if 'calc_df' not in st.session_state:
                reset_calc_area()

            # Cria uma chave única para o editor baseada no arquivo atual
            editor_key = f"calc_table_{st.session_state.get('last_file', 'initial')}"

            # Garante que o DataFrame está com os tipos corretos antes da edição
            current_df = st.session_state.calc_df.astype({
                'Descrição': 'string',
                'Valor': 'float64'
            })

            edited_df = st.data_editor(
                current_df,
                column_config={
                    "Descrição": st.column_config.TextColumn(
                        "Descrição",
                        width="medium",
                    ),
                    "Valor": st.column_config.NumberColumn(
                        "Valor",
                        format="R$ %.2f",
                        width="small",
                        step=0.01,  # Adiciona controle mais preciso para números decimais
                    ),
                },
                num_rows="dynamic",
                key=editor_key
            )

            # Garante que o DataFrame editado mantenha os tipos corretos
            if not edited_df.equals(current_df):
                edited_df = edited_df.astype({
                    'Descrição': 'string',
                    'Valor': 'float64'
                })
                st.session_state.calc_df = edited_df.copy()


            # Atualiza o DataFrame na session_state apenas se houver mudanças
            if not edited_df.equals(st.session_state.calc_df):
                st.session_state.calc_df = edited_df.copy()

                      

            # Atualiza o DataFrame na session_state
            st.session_state.calc_df = edited_df  # Esta linha vai aqui, logo após o data_editor

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

            else:  # Publisher
                status_filter = st.multiselect(
                    "Filtrar por Status",
                    options=['Adquirida', 'Não Adquirida'],
                    default=['Adquirida', 'Não Adquirida'],
                    key="publisher_filter"
                )
                
                # Monta os filtros baseado nas seleções
                acquired_mask = (df_obras['AQUIRED'] == 'Y') if 'Adquirida' in status_filter else False
                not_acquired_mask = (df_obras['AQUIRED'] == 'N') if 'Não Adquirida' in status_filter else False
                
                df_obras_filtered = df_obras[
                    acquired_mask | not_acquired_mask
                ].copy()

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
