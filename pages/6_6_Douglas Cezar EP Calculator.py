import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import os

# Configurações pré-determinadas
AUTOR = "Douglas Cezar"
EDITORA = "DC Editora"
OBRAS_PATH = os.path.join("data", "catalogs", "douglas-cezar", "obras-cadastradas-DOUGLAS-CEZAR.xlsx")

# Shares pré-definidos
WRITER_SHARE = 0.5
NNC_WRITER_SHARE = 0.5
PUBLISHER_TOTAL_SHARE = 0.5
NNC_PUBLISHER_SHARE = 0.5
PUBLISHER_ADMIN_SHARE = 0.4
NNC_ADMIN_SHARE = 0.6

def get_regras(periodo):
    """Retorna as regras com o período informado"""
    return {
        ("DOUGLAS CEZAR", "Writer Share"): [
            {"Contract - Money In": "ABRAMUS"},
            {"nome_income1": periodo + " EXECUCAO PUBLICA - DOUGLAS CEZAR - NN AQUISICAO (50%)"},
            {"nome_income2": periodo + " EXECUCAO PUBLICA - DOUGLAS CEZAR - RECUPERAVEL (50%)"},
            {"Contract - Money Out": "NAS NUVENS (WS) - DOUGLAS CEZAR (37,5%)"},
            {"SPLIT AMOUNT | Organization (%)": 0},
            {"SPLIT AMOUNT | Rights-Holder (%)": 50},
            {"Contract - Money Out": "DOUGLAS CEZAR AQUISIÇÃO (37,5%)"},
            {"SPLIT AMOUNT | Organization (%)": 0},
            {"SPLIT AMOUNT | Rights-Holder (%)": 50}
        ],
        ("DOUGLAS CEZAR", "Publisher Share"): [
            {"Contract - Money In": "ABRAMUS"},
            {"nome_income1": periodo + " EXECUCAO PUBLICA - DOUGLAS CEZAR / DC EDICOES - NN AQUISICAO (50%)"},
            {"nome_income2": periodo + " EXECUCAO PUBLICA - DOUGLAS CEZAR / DC EDICOES - NN RECUPERAVEL (50%)"},
            {"Contract - Money Out": "NAS NUVENS (PS) - DOUGLAS CEZAR - DC PRODUÇÕES (12,5%)"},
            {"SPLIT AMOUNT | Organization (%)": 0},
            {"SPLIT AMOUNT | Rights-Holder (%)": 50},
            {"Contract - Money Out": "DC PRODUÇÕES (DOUGLAS CEZAR) (PS) (12,5%)"},
            {"SPLIT AMOUNT | Organization (%)": 30},
            {"SPLIT AMOUNT | Rights-Holder (%)": 20}
        ]
    }

def format_currency(value):
    """Formata valor numérico com separadores de milhar e decimais"""
    try:
        if isinstance(value, str):
            value = float(value.replace('R$', '').replace('.', '').replace(',', '.').strip())
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return value

class ProcessadorRoyalties:
    def __init__(self, obras_cadastradas, tipo_relatorio):
        self.obras_cadastradas = obras_cadastradas
        self.tipo_relatorio = tipo_relatorio
        self.autor = AUTOR
        self.editora = EDITORA
        
        if tipo_relatorio == "Writer":
            self.writer_share = WRITER_SHARE
            self.nnc_writer_share = NNC_WRITER_SHARE
            self.publisher_share = 0
            self.nnc_publisher_share = 0
            self.publisher_admin_share = 0
            self.nnc_admin_share = 0
        else:
            self.writer_share = 0
            self.nnc_writer_share = 0
            self.publisher_share = PUBLISHER_TOTAL_SHARE
            self.nnc_publisher_share = NNC_PUBLISHER_SHARE
            self.publisher_admin_share = PUBLISHER_ADMIN_SHARE
            self.nnc_admin_share = NNC_ADMIN_SHARE

    def processar_relatorio(self, relatorio):
        """Processa o relatório (pode conter nacional, internacional ou ambos) e retorna os resultados calculados"""
        
        # Identifica quais tipos de relatório estão presentes
        tem_nacional = 'CÓD. OBRA' in relatorio.columns and 'RATEIO' in relatorio.columns
        tem_internacional = 'ISRC/ISWC' in relatorio.columns and 'Rendimento' in relatorio.columns
        
        dfs_obras_processadas = []
        
        # Processa relatório NACIONAL se existir
        if tem_nacional:
            df_nacional = relatorio[relatorio['CÓD. OBRA'].notna()].copy()
            if not df_nacional.empty:
                # Agrupa por código e título, somando os valores
                df_obras_nac = df_nacional.groupby(['CÓD. OBRA', 'TÍTULO DA MUSICA']).agg({
                    'RATEIO': 'sum'
                }).reset_index()
                df_obras_nac = df_obras_nac.rename(columns={'RATEIO': 'TOTAL'})
                
                # Faz merge com obras cadastradas
                df_obras_nac = df_obras_nac.merge(
                    self.obras_cadastradas[['CÓD. OBRA', 'AQUIRED', 'CONTROLLED']],
                    on='CÓD. OBRA',
                    how='inner'
                )
                
                if not df_obras_nac.empty:
                    dfs_obras_processadas.append(df_obras_nac)
        
        # Processa relatório INTERNACIONAL se existir  
        if tem_internacional:
            df_inter = relatorio[relatorio['ISRC/ISWC'].notna()].copy()
            if not df_inter.empty:
                # Identifica o nome correto da coluna de título
                coluna_titulo_inter = 'Título' if 'Título' in df_inter.columns else 'TITULOTITULO'
                
                # Agrupa por ISWC e título, somando os valores
                df_obras_inter = df_inter.groupby(['ISRC/ISWC', coluna_titulo_inter]).agg({
                    'Rendimento': 'sum'
                }).reset_index()
                df_obras_inter = df_obras_inter.rename(columns={'Rendimento': 'TOTAL'})
                
                # Faz merge com obras cadastradas usando ISWC
                df_obras_inter = df_obras_inter.merge(
                    self.obras_cadastradas[['ISWC', 'AQUIRED', 'CONTROLLED']],
                    left_on='ISRC/ISWC',
                    right_on='ISWC',
                    how='inner'
                )
                
                # Renomeia colunas para padronizar com nacional
                rename_dict = {'ISRC/ISWC': 'CÓD. OBRA'}
                rename_dict[coluna_titulo_inter] = 'TÍTULO DA MUSICA'
                df_obras_inter = df_obras_inter.rename(columns=rename_dict)
                
                if not df_obras_inter.empty:
                    dfs_obras_processadas.append(df_obras_inter)
        
        # Se não há obras processadas, retorna vazio
        if not dfs_obras_processadas:
            if self.tipo_relatorio == "Writer":
                return pd.DataFrame(columns=['TITULAR', 'PERCENTUAL', 'TOTAL CALCULADO']), \
                       pd.DataFrame(), []
            else:
                return pd.DataFrame(columns=['TITULAR', 'PERCENTUAL', 'TOTAL CALCULADO']), \
                       pd.DataFrame(columns=['TITULAR', 'PERCENTUAL', 'TOTAL CALCULADO']), \
                       pd.DataFrame(), []
        
        # Combina as obras processadas de nacional e internacional
        df_obras = pd.concat(dfs_obras_processadas, ignore_index=True)
        
        # Agrupa novamente caso a mesma obra apareça em ambos os relatórios
        # (usa CÓD. OBRA que agora contém tanto códigos nacionais quanto ISWCs)
        df_obras = df_obras.groupby(['CÓD. OBRA', 'TÍTULO DA MUSICA']).agg({
            'TOTAL': 'sum',
            'AQUIRED': 'first',
            'CONTROLLED': 'first'
        }).reset_index()
        
        # Calcula resultados baseado no tipo de relatório
        if self.tipo_relatorio == "Writer":
            resultados = []
            for _, obra in df_obras.iterrows():
                if obra['AQUIRED'] == 'Y':
                    resultados.extend([
                        {
                            'TITULAR': f'{self.autor} (Writer Share)',
                            'PERCENTUAL': self.writer_share * 100,
                            'TOTAL CALCULADO': round(obra['TOTAL'] * self.writer_share, 2)
                        },
                        {
                            'TITULAR': 'NN Aquisição (Writer Share)',
                            'PERCENTUAL': self.nnc_writer_share * 100,
                            'TOTAL CALCULADO': round(obra['TOTAL'] * self.nnc_writer_share, 2)
                        }
                    ])
                else:
                    resultados.append({
                        'TITULAR': 'Não Adquiridos (Writer Share) - Amortização',
                        'PERCENTUAL': 100.0,
                        'TOTAL CALCULADO': round(obra['TOTAL'], 2)
                    })
            
            df_titulares = pd.DataFrame(resultados)
            df_titulares = df_titulares.groupby('TITULAR').agg({
                'PERCENTUAL': 'first',
                'TOTAL CALCULADO': 'sum'
            }).reset_index()
            
            return df_titulares, df_obras, resultados
            
        else:  # Publisher
            resultados_aquisicao = []
            resultados_administracao = []
            
            for _, obra in df_obras.iterrows():
                if obra['AQUIRED'] == 'Y':
                    # Todas as obras ADQUIRIDAS vão para AQUISIÇÃO
                    resultados_aquisicao.extend([
                        {
                            'TITULAR': f'{self.editora} (Publisher Share)',
                            'PERCENTUAL': self.publisher_share * self.publisher_admin_share * 100,
                            'TOTAL CALCULADO': round(obra['TOTAL'] * self.publisher_share * self.publisher_admin_share, 2)
                        },
                        {
                            'TITULAR': 'NN Aquisição (Publisher Share)',
                            'PERCENTUAL': self.nnc_publisher_share * 100,
                            'TOTAL CALCULADO': round(obra['TOTAL'] * self.nnc_publisher_share, 2)
                        },
                        {
                            'TITULAR': 'NN Fee (Admin)',
                            'PERCENTUAL': self.publisher_share * self.nnc_admin_share * 100,
                            'TOTAL CALCULADO': round(obra['TOTAL'] * self.publisher_share * self.nnc_admin_share, 2)
                        }
                    ])
                else:
                    # Todas as obras NÃO ADQUIRIDAS vão para ADMINISTRAÇÃO
                    # AQUIRED=N: Administração pura (sem aquisição)
                    # Distribui TODO o valor: NN Fee (60%) + DC Editora (40%)
                    resultados_administracao.extend([
                        {
                            'TITULAR': f'{self.editora} (Publisher Share)',
                            'PERCENTUAL': self.publisher_admin_share * 100,
                            'TOTAL CALCULADO': round(obra['TOTAL'] * self.publisher_admin_share, 2)
                        },
                        {
                            'TITULAR': 'NN Fee (Admin)',
                            'PERCENTUAL': self.nnc_admin_share * 100,
                            'TOTAL CALCULADO': round(obra['TOTAL'] * self.nnc_admin_share, 2)
                        }
                    ])
            
            df_titulares_aquisicao = pd.DataFrame(resultados_aquisicao)
            if not df_titulares_aquisicao.empty:
                df_titulares_aquisicao = df_titulares_aquisicao.groupby('TITULAR').agg({
                    'PERCENTUAL': 'first',
                    'TOTAL CALCULADO': 'sum'
                }).reset_index()
            
            df_titulares_administracao = pd.DataFrame(resultados_administracao)
            if not df_titulares_administracao.empty:
                df_titulares_administracao = df_titulares_administracao.groupby('TITULAR').agg({
                    'PERCENTUAL': 'first',
                    'TOTAL CALCULADO': 'sum'
                }).reset_index()
            
            # Combina todos os resultados para retornar
            resultados = resultados_aquisicao + resultados_administracao
            
            return df_titulares_aquisicao, df_titulares_administracao, df_obras, resultados

def gerar_linhas_incomes(df_titulares, tipo_relatorio, periodo, total_nao_adquiridas=0, total_geral_real=None):
    """Gera as linhas de incomes no formato do sistema externo
    
    Args:
        df_titulares: DataFrame com os totais por titular
        tipo_relatorio: "Writer" ou "Publisher"
        periodo: String com o período (ex: "2025M8")
        total_nao_adquiridas: Total de obras não adquiridas (usado no Writer)
        total_geral_real: Total geral real para usar no Gross Amount (usado no Publisher para consolidar Aquisição + Administração)
    """
    incomes = []
    
    if tipo_relatorio == "Writer":
        # Para Writer: Gera 2 linhas de income (Aquisição + Recuperável) e 2 linhas de money out
        regras = get_regras(periodo)
        regra_writer = regras.get(("DOUGLAS CEZAR", "Writer Share"))
        
        if regra_writer:
            contract_money_in = regra_writer[0]["Contract - Money In"]
            nome_income1 = regra_writer[1]["nome_income1"]
            nome_income2 = regra_writer[2]["nome_income2"]
            
            # Separa os valores corretamente
            # Linha 1: NN Aquisição (Writer Share) - vai para NAS NUVENS (WS)
            total_nnc_acquirer = df_titulares[df_titulares['TITULAR'].str.contains('NN Aquisição \(Writer Share\)', na=False, regex=True)]['TOTAL CALCULADO'].sum()
            
            # Linha 2: Douglas Cezar (Writer Share) + Não Adquiridos - vai para DOUGLAS CEZAR AQUISIÇÃO
            total_douglas = df_titulares[df_titulares['TITULAR'].str.contains('Douglas Cezar', na=False)]['TOTAL CALCULADO'].sum()
            total_nao_adquiridos = df_titulares[df_titulares['TITULAR'].str.contains('Não Adquiridos \(Writer Share\) - Amortização', na=False, regex=True)]['TOTAL CALCULADO'].sum()
            total_recuperavel = total_douglas + total_nao_adquiridos
            
            # Total geral - usa o total_geral_real se foi fornecido, senão calcula
            if total_geral_real is not None:
                total_geral_arredondado = round(total_geral_real, 2)
            else:
                total_geral = total_nnc_acquirer + total_recuperavel
                total_geral_arredondado = round(total_geral, 2)
            
            # Arredonda o primeiro Net Amount
            net_amount_1 = round(total_nnc_acquirer, 2)
            
            # Segundo Net Amount é ajustado para que a soma = Gross Amount exato
            net_amount_2 = round(total_geral_arredondado - net_amount_1, 2)
            
            # Income 1 - Aquisição (50%) - NAS NUVENS
            incomes.append({
                'Name (*)': nome_income1,
                'Contract - Money In (*)': contract_money_in,
                'Sale Date (*)': '',
                'Payment Date (*)': '',
                'Net Amount (*)': net_amount_1,
                'Gross Amount': total_geral_arredondado,
                'Foreign Currency': '',
                'Foreign Net Amount': '',
                'Foreign Gross Amount': '',
                'Contract - Money Out (*)': regra_writer[3]["Contract - Money Out"],
                'SPLIT AMOUNT | Organization (*)': 0,
                'SPLIT AMOUNT | Rights-Holder (*)': net_amount_1,
                'Notes': f"Org: 0% | Rights: 50%"
            })
            
            # Income 2 - Recuperável (50%) - DOUGLAS CEZAR AQUISIÇÃO
            incomes.append({
                'Name (*)': nome_income2,
                'Contract - Money In (*)': contract_money_in,
                'Sale Date (*)': '',
                'Payment Date (*)': '',
                'Net Amount (*)': net_amount_2,
                'Gross Amount': total_geral_arredondado,
                'Foreign Currency': '',
                'Foreign Net Amount': '',
                'Foreign Gross Amount': '',
                'Contract - Money Out (*)': regra_writer[6]["Contract - Money Out"],
                'SPLIT AMOUNT | Organization (*)': 0,
                'SPLIT AMOUNT | Rights-Holder (*)': net_amount_2,
                'Notes': f"Org: 0% | Rights: 50%"
            })
    
    else:  # Publisher
        # Para Publisher: Gera 2 linhas de income (Aquisição + Recuperável)
        regras = get_regras(periodo)
        regra_publisher = regras.get(("DOUGLAS CEZAR", "Publisher Share"))
        
        if regra_publisher:
            contract_money_in = regra_publisher[0]["Contract - Money In"]
            nome_income1 = regra_publisher[1]["nome_income1"]
            nome_income2 = regra_publisher[2]["nome_income2"]
            
            # Linha 1: Apenas NN Aquisição (Publisher Share) - vai para NAS NUVENS (PS)
            total_nnc_acquirer = df_titulares[df_titulares['TITULAR'].str.contains('NN Aquisição \(Publisher Share\)', na=False, regex=True)]['TOTAL CALCULADO'].sum()
            
            # Linha 2: TODO O RESTO (DC Editora + NN Fee + outros NNC) - vai para DC PRODUÇÕES
            # Organization = NN Fee (Admin)
            # Rights-Holder = DC Editora (Publisher Share)
            total_admin = df_titulares[df_titulares['TITULAR'].str.contains('NN Fee \(Admin\)', na=False, regex=True)]['TOTAL CALCULADO'].sum()
            total_dc = df_titulares[df_titulares['TITULAR'].str.contains('DC Editora \(Publisher Share\)', na=False, regex=True)]['TOTAL CALCULADO'].sum()
            
            # Outros NNC que não são NN Aquisição
            total_nnc_outros = df_titulares[
                (df_titulares['TITULAR'].str.contains('NNC', na=False) | df_titulares['TITULAR'].str.contains('Não Adquiridos', na=False)) & 
                (~df_titulares['TITULAR'].str.contains('NN Aquisição \(Publisher Share\)', na=False, regex=True))
            ]['TOTAL CALCULADO'].sum()
            
            # Total Recuperável = tudo que não é NN Aquisição
            total_recuperavel = total_dc + total_admin + total_nnc_outros
            
            # Total geral - usa o total_geral_real se foi fornecido (para consolidação), senão calcula
            if total_geral_real is not None:
                total_geral = total_geral_real
            else:
                total_geral = total_nnc_acquirer + total_recuperavel
            
            total_geral_arredondado = round(total_geral, 2)
            
            # Arredonda o primeiro Net Amount
            net_amount_1 = round(total_nnc_acquirer, 2)
            
            # Segundo Net Amount é ajustado para que a soma = Gross Amount exato
            net_amount_2 = round(total_geral_arredondado - net_amount_1, 2)
            
            # Para os splits da linha 2, arredonda Organization primeiro e ajusta Rights-Holder
            split_org = round(total_admin, 2)
            split_rights = round(net_amount_2 - split_org, 2)
            
            # Income 1 - Aquisição (50%) - NAS NUVENS
            incomes.append({
                'Name (*)': nome_income1,
                'Contract - Money In (*)': contract_money_in,
                'Sale Date (*)': '',
                'Payment Date (*)': '',
                'Net Amount (*)': net_amount_1,
                'Gross Amount': total_geral_arredondado,
                'Foreign Currency': '',
                'Foreign Net Amount': '',
                'Foreign Gross Amount': '',
                'Contract - Money Out (*)': regra_publisher[3]["Contract - Money Out"],
                'SPLIT AMOUNT | Organization (*)': 0,
                'SPLIT AMOUNT | Rights-Holder (*)': net_amount_1,
                'Notes': f"Org: 0% | Rights: 50%"
            })
            
            # Income 2 - Recuperável (50%) - DC PRODUÇÕES
            # Organization = NN Fee (Admin)
            # Rights-Holder = DC Editora (Publisher Share)
            incomes.append({
                'Name (*)': nome_income2,
                'Contract - Money In (*)': contract_money_in,
                'Sale Date (*)': '',
                'Payment Date (*)': '',
                'Net Amount (*)': net_amount_2,
                'Gross Amount': total_geral_arredondado,
                'Foreign Currency': '',
                'Foreign Net Amount': '',
                'Foreign Gross Amount': '',
                'Contract - Money Out (*)': regra_publisher[6]["Contract - Money Out"],
                'SPLIT AMOUNT | Organization (*)': split_org,
                'SPLIT AMOUNT | Rights-Holder (*)': split_rights,
                'Notes': f"Org (NN Fee): {split_org:.2f} | Rights (DC Editora): {split_rights:.2f}"
            })
    
    return pd.DataFrame(incomes)

def main():
    st.set_page_config(page_title="Royalties Processor - Douglas Cezar & DC Editora", layout="wide")
    
    st.title("Processador de Royalties")
    st.subheader(f"Autor: {AUTOR} | Editora: {EDITORA}")
    
    # Inicializa session_state para manter os dados
    if 'dados_processados' not in st.session_state:
        st.session_state.dados_processados = None
    
    # Campo de entrada do período
    periodo = st.text_input("Período para nomes de incomes", "2025M8")
    
    try:
        obras_cadastradas = pd.read_excel(OBRAS_PATH)
        st.success(f"Obras cadastradas carregadas: {len(obras_cadastradas)} obras")
    except Exception as e:
        st.error(f"Erro ao carregar obras cadastradas: {str(e)}")
        return

    st.header("Upload de Relatórios")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Douglas Cezar (Writer)")
        uploaded_nacional_writer = st.file_uploader(
            "Relatório Nacional (CSV)", 
            type=['csv'],
            key="nacional_writer"
        )
        uploaded_internacional_writer = st.file_uploader(
            "Relatório Internacional (Excel)", 
            type=['xlsx', 'xls'],
            key="internacional_writer"
        )
    
    with col2:
        st.subheader("DC Editora (Publisher)")
        uploaded_nacional_publisher = st.file_uploader(
            "Relatório Nacional (CSV)", 
            type=['csv'],
            key="nacional_publisher"
        )
        uploaded_internacional_publisher = st.file_uploader(
            "Relatório Internacional (Excel)", 
            type=['xlsx', 'xls'],
            key="internacional_publisher"
        )

    if st.button("Processar Relatórios", type="primary"):
        # Carrega relatórios Writer
        relatorios_writer = []
        if uploaded_nacional_writer:
            relatorios_writer.append(pd.read_csv(
                uploaded_nacional_writer,
                sep=';',
                encoding="ISO-8859-1",
                decimal=',',
                thousands='.',
                header=4
            ))
        if uploaded_internacional_writer:
            relatorios_writer.append(pd.read_excel(uploaded_internacional_writer))
        
        # Carrega relatórios Publisher
        relatorios_publisher = []
        if uploaded_nacional_publisher:
            relatorios_publisher.append(pd.read_csv(
                uploaded_nacional_publisher,
                sep=';',
                encoding="ISO-8859-1",
                decimal=',',
                thousands='.',
                header=4
            ))
        if uploaded_internacional_publisher:
            relatorios_publisher.append(pd.read_excel(uploaded_internacional_publisher))
        
        if not relatorios_writer and not relatorios_publisher:
            st.warning("Nenhum relatório foi carregado")
            return
        
        try:
            # Dicionário para armazenar todos os dados processados
            dados = {
                'writer': None,
                'publisher': None
            }
            # Processa Writer se houver relatórios
            if relatorios_writer:
                # Concatena TODOS os relatórios primeiro (nacional + internacional)
                relatorio_writer_completo = pd.concat(relatorios_writer, ignore_index=True)
                processador_writer = ProcessadorRoyalties(obras_cadastradas, "Writer")
                
                # Calcula totais separados para exibição
                total_nacional_writer = 0
                total_internacional_writer = 0
                
                for i, rel in enumerate(relatorios_writer):
                    if 'RATEIO' in rel.columns and 'CÓD. OBRA' in rel.columns:  # Nacional
                        total_nacional_writer += rel['RATEIO'].sum()
                    elif 'Rendimento' in rel.columns:  # Internacional
                        total_internacional_writer += rel['Rendimento'].sum()
                
                # Total geral considerando ambas as colunas
                total_geral_writer = 0
                if 'RATEIO' in relatorio_writer_completo.columns:
                    total_geral_writer += relatorio_writer_completo['RATEIO'].fillna(0).sum()
                if 'Rendimento' in relatorio_writer_completo.columns:
                    total_geral_writer += relatorio_writer_completo['Rendimento'].fillna(0).sum()
                
                # Processa o relatório completo (nacional + internacional juntos)
                df_titulares_writer, df_obras_writer, resultados_writer = processador_writer.processar_relatorio(relatorio_writer_completo)
                
                total_acquired_writer = df_obras_writer[df_obras_writer['AQUIRED'] == 'Y']['TOTAL'].sum()
                total_nao_acquired_writer = df_obras_writer[df_obras_writer['AQUIRED'] == 'N']['TOTAL'].sum()
                total_processado_writer = df_obras_writer['TOTAL'].sum()
                total_nao_processado_writer = total_geral_writer - total_processado_writer
                
                df_incomes_writer = gerar_linhas_incomes(df_titulares_writer, "Writer", periodo, total_nao_acquired_writer, total_processado_writer)
                
                # Salva dados do Writer no session_state
                dados['writer'] = {
                    'total_nacional': total_nacional_writer,
                    'total_internacional': total_internacional_writer,
                    'total_geral': total_geral_writer,
                    'total_processado': total_processado_writer,
                    'total_acquired': total_acquired_writer,
                    'total_nao_acquired': total_nao_acquired_writer,
                    'total_nao_processado': total_nao_processado_writer,
                    'qtd_obras': len(df_obras_writer),
                    'df_titulares': df_titulares_writer,
                    'df_obras': df_obras_writer,
                    'df_incomes': df_incomes_writer
                }
            
            # Processa Publisher se houver relatórios
            if relatorios_publisher:
                # Concatena TODOS os relatórios primeiro (nacional + internacional)
                relatorio_publisher_completo = pd.concat(relatorios_publisher, ignore_index=True)
                processador_publisher = ProcessadorRoyalties(obras_cadastradas, "Publisher")
                
                # Calcula totais separados para exibição
                total_nacional_publisher = 0
                total_internacional_publisher = 0
                
                for i, rel in enumerate(relatorios_publisher):
                    if 'RATEIO' in rel.columns and 'CÓD. OBRA' in rel.columns:  # Nacional
                        total_nacional_publisher += rel['RATEIO'].sum()
                    elif 'Rendimento' in rel.columns:  # Internacional
                        total_internacional_publisher += rel['Rendimento'].sum()
                
                # Total geral considerando ambas as colunas
                total_geral_publisher = 0
                if 'RATEIO' in relatorio_publisher_completo.columns:
                    total_geral_publisher += relatorio_publisher_completo['RATEIO'].fillna(0).sum()
                if 'Rendimento' in relatorio_publisher_completo.columns:
                    total_geral_publisher += relatorio_publisher_completo['Rendimento'].fillna(0).sum()
                
                # Processa o relatório completo (nacional + internacional juntos)
                df_titulares_aquisicao, df_titulares_administracao, df_obras_publisher, resultados_publisher = processador_publisher.processar_relatorio(relatorio_publisher_completo)
                
                total_acquired_publisher = df_obras_publisher[df_obras_publisher['AQUIRED'] == 'Y']['TOTAL'].sum()
                total_nao_acquired_publisher = df_obras_publisher[df_obras_publisher['AQUIRED'] == 'N']['TOTAL'].sum()
                total_processado_publisher = df_obras_publisher['TOTAL'].sum()
                total_nao_processado_publisher = total_geral_publisher - total_processado_publisher
                
                # Gera incomes passando o total_processado_publisher como total_geral_real
                # para que ambas as tabelas (aquisição e administração) usem o mesmo Gross Amount
                df_incomes_aquisicao = gerar_linhas_incomes(
                    df_titulares_aquisicao, "Publisher", periodo, 
                    total_geral_real=total_processado_publisher
                ) if not df_titulares_aquisicao.empty else None
                
                df_incomes_administracao = gerar_linhas_incomes(
                    df_titulares_administracao, "Publisher", periodo,
                    total_geral_real=total_processado_publisher
                ) if not df_titulares_administracao.empty else None
                
                # Combina as incomes de aquisição e administração em uma única tabela consolidada
                df_incomes_consolidado = None
                if df_incomes_aquisicao is not None and df_incomes_administracao is not None:
                    # Combina os dois DataFrames
                    # A linha de NN AQUISICAO vem apenas da aquisição (linha 0)
                    # A linha de NN RECUPERAVEL (linha 1) soma aquisição + administração
                    df_incomes_consolidado = df_incomes_aquisicao.copy()
                    
                    # Identifica qual linha da administração é a RECUPERAVEL
                    # Se administração tem 2 linhas, RECUPERAVEL é a linha 1
                    # Se administração tem 1 linha, RECUPERAVEL é a linha 0
                    idx_recuperavel_admin = 1 if len(df_incomes_administracao) > 1 else 0
                    
                    # Soma os valores da linha RECUPERAVEL
                    df_incomes_consolidado.loc[1, 'Net Amount (*)'] += df_incomes_administracao.loc[idx_recuperavel_admin, 'Net Amount (*)']
                    df_incomes_consolidado.loc[1, 'SPLIT AMOUNT | Organization (*)'] += df_incomes_administracao.loc[idx_recuperavel_admin, 'SPLIT AMOUNT | Organization (*)']
                    df_incomes_consolidado.loc[1, 'SPLIT AMOUNT | Rights-Holder (*)'] += df_incomes_administracao.loc[idx_recuperavel_admin, 'SPLIT AMOUNT | Rights-Holder (*)']
                elif df_incomes_aquisicao is not None:
                    df_incomes_consolidado = df_incomes_aquisicao
                elif df_incomes_administracao is not None:
                    # Se só tem administração, cria uma linha de NN AQUISICAO zerada e uma de RECUPERAVEL
                    regras = get_regras(periodo)
                    regra_publisher = regras.get(("DOUGLAS CEZAR", "Publisher Share"))
                    if regra_publisher:
                        contract_money_in = regra_publisher[0]["Contract - Money In"]
                        nome_income1 = regra_publisher[1]["nome_income1"]
                        
                        # Identifica a linha de RECUPERAVEL na administração
                        idx_recuperavel_admin = 1 if len(df_incomes_administracao) > 1 else 0
                        total_geral = df_incomes_administracao.loc[idx_recuperavel_admin, 'Gross Amount']
                        
                        # Linha de NN AQUISICAO zerada
                        linha_aquisicao = {
                            'Name (*)': nome_income1,
                            'Contract - Money In (*)': contract_money_in,
                            'Sale Date (*)': '',
                            'Payment Date (*)': '',
                            'Net Amount (*)': 0.0,
                            'Gross Amount': total_geral,
                            'Foreign Currency': '',
                            'Foreign Net Amount': '',
                            'Foreign Gross Amount': '',
                            'Contract - Money Out (*)': regra_publisher[3]["Contract - Money Out"],
                            'SPLIT AMOUNT | Organization (*)': 0,
                            'SPLIT AMOUNT | Rights-Holder (*)': 0.0,
                            'Notes': f"Org: 0% | Rights: 50%"
                        }
                        df_incomes_consolidado = pd.concat([pd.DataFrame([linha_aquisicao]), df_incomes_administracao.iloc[[idx_recuperavel_admin]].reset_index(drop=True)], ignore_index=True)
                
                # Salva dados do Publisher no session_state
                dados['publisher'] = {
                    'total_nacional': total_nacional_publisher,
                    'total_internacional': total_internacional_publisher,
                    'total_geral': total_geral_publisher,
                    'total_processado': total_processado_publisher,
                    'total_acquired': total_acquired_publisher,
                    'total_nao_acquired': total_nao_acquired_publisher,
                    'total_nao_processado': total_nao_processado_publisher,
                    'qtd_obras': len(df_obras_publisher),
                    'df_titulares_aquisicao': df_titulares_aquisicao,
                    'df_titulares_administracao': df_titulares_administracao,
                    'df_obras': df_obras_publisher,
                    'df_incomes_aquisicao': df_incomes_aquisicao,
                    'df_incomes_administracao': df_incomes_administracao,
                    'df_incomes_consolidado': df_incomes_consolidado
                }
            
            # Salva dados no session_state
            st.session_state.dados_processados = dados
            st.success("Relatórios processados com sucesso!")
            
        except Exception as e:
            st.error(f"Erro ao processar relatórios: {str(e)}")
            st.exception(e)
    
    # Exibe os dados processados (sempre visível após processamento)
    if st.session_state.dados_processados:
        dados = st.session_state.dados_processados
        
        # Exibe Writer se houver dados
        if dados['writer']:
            st.header("Resultados - Writer (Douglas Cezar)")
            d = dados['writer']
            
            # Exibe métricas com separação Nacional/Internacional
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if d['total_nacional'] > 0:
                    st.metric("Total Nacional", format_currency(d['total_nacional']))
                if d['total_internacional'] > 0:
                    st.metric("Total Internacional", format_currency(d['total_internacional']))
            
            with col2:
                st.metric("Total Geral", format_currency(d['total_geral']))
                st.metric("Total Processado", format_currency(d['total_processado']))
            
            with col3:
                st.metric("Obras Adquiridas", format_currency(d['total_acquired']))
                st.metric("Obras Não Adquiridas", format_currency(d['total_nao_acquired']), 
                         delta_color="inverse")
            
            with col4:
                if d['total_nao_processado'] > 0:
                    st.metric("Não Processado", format_currency(d['total_nao_processado']),
                             delta_color="inverse")
                st.metric("Quantidade de Obras", d['qtd_obras'])
            
            st.subheader("Resumo por Titular")
            df_titulares_display = d['df_titulares'].copy()
            
            # Adiciona linha de total
            total_row = pd.DataFrame([{
                'TITULAR': 'TOTAL',
                'PERCENTUAL': '',
                'TOTAL CALCULADO': df_titulares_display['TOTAL CALCULADO'].sum()
            }])
            df_titulares_display = pd.concat([df_titulares_display, total_row], ignore_index=True)
            
            # Formata percentual
            df_titulares_display['PERCENTUAL'] = df_titulares_display['PERCENTUAL'].apply(
                lambda x: f"{x:.1f}%" if isinstance(x, (int, float)) else x
            )
            
            # Aplica estilo - vermelho clarinho para linha TOTAL
            def highlight_total(row):
                if row['TITULAR'] == 'TOTAL':
                    return ['background-color: #ffe6e6; font-weight: bold'] * len(row)
                return [''] * len(row)
            
            st.dataframe(
                df_titulares_display.style.format({
                    'TOTAL CALCULADO': format_currency
                }).apply(highlight_total, axis=1),
                hide_index=True,
                use_container_width=True
            )
            
            st.subheader("Linhas de Incomes para Sistema Externo")
            st.dataframe(
                d['df_incomes'],
                hide_index=True,
                use_container_width=True
            )
            
            # Validação das Incomes
            st.caption("🔍 Validação dos Valores")
            
            total_geral = d['total_geral']
            df_incomes = d['df_incomes']
            
            # Check 1: Gross Amount bate com Total Geral
            gross_amount_income = df_incomes['Gross Amount'].iloc[0] if len(df_incomes) > 0 else 0
            check1 = abs(gross_amount_income - total_geral) < 0.01
            
            # Check 2: Soma dos Net Amount bate com Gross Amount (tolerância de 0.02 para arredondamento)
            soma_net_amount = df_incomes['Net Amount (*)'].sum()
            check2 = abs(soma_net_amount - gross_amount_income) < 0.02
            
            # Check 3: Splits batem com Net Amount
            check3_list = []
            for _, row in df_incomes.iterrows():
                soma_splits = row['SPLIT AMOUNT | Organization (*)'] + row['SPLIT AMOUNT | Rights-Holder (*)']
                net_amount = row['Net Amount (*)']
                check3_list.append(abs(soma_splits - net_amount) < 0.02)
            check3 = all(check3_list)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Gross Amount = Total Geral",
                    "✅" if check1 else "❌",
                    f"{format_currency(gross_amount_income)} = {format_currency(total_geral)}"
                )
            with col2:
                st.metric(
                    "Soma Net Amount = Gross Amount",
                    "✅" if check2 else "❌",
                    f"{format_currency(soma_net_amount)}"
                )
            with col3:
                st.metric(
                    "Splits = Net Amount",
                    "✅" if check3 else "❌",
                    f"{len([x for x in check3_list if x])}/{len(check3_list)} linhas"
                )
            
            st.divider()
            st.subheader("Detalhamento de Obras")
            
            status_filter_writer = st.multiselect(
                "Filtrar por Status",
                options=['Y', 'N'],
                default=['Y', 'N'],
                format_func=lambda x: "Adquirida" if x == 'Y' else "Não Adquirida",
                key="status_filter_writer"
            )
            
            # Se nenhum filtro for selecionado, mostra todas
            if not status_filter_writer:
                status_filter_writer = ['Y', 'N']
            
            df_obras_writer_filtered = d['df_obras'][d['df_obras']['AQUIRED'].isin(status_filter_writer)].copy()
            df_obras_writer_filtered = df_obras_writer_filtered.sort_values('TOTAL', ascending=False)
            
            st.dataframe(
                df_obras_writer_filtered.style.format({
                    'TOTAL': format_currency
                }),
                hide_index=True,
                use_container_width=True
            )
            
            st.divider()
        
        # Exibe Publisher se houver dados
        if dados['publisher']:
            st.header("Resultados - Publisher (DC Editora)")
            d = dados['publisher']
            
            # Exibe métricas com separação Nacional/Internacional
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if d['total_nacional'] > 0:
                    st.metric("Total Nacional", format_currency(d['total_nacional']))
                if d['total_internacional'] > 0:
                    st.metric("Total Internacional", format_currency(d['total_internacional']))
            
            with col2:
                st.metric("Total Geral", format_currency(d['total_geral']))
                st.metric("Total Processado", format_currency(d['total_processado']))
            
            with col3:
                st.metric("Obras Adquiridas", format_currency(d['total_acquired']))
                st.metric("Obras Não Adquiridas", format_currency(d['total_nao_acquired']), 
                         delta_color="inverse")
            
            with col4:
                if d['total_nao_processado'] > 0:
                    st.metric("Não Processado", format_currency(d['total_nao_processado']),
                             delta_color="inverse")
                st.metric("Quantidade de Obras", d['qtd_obras'])
            
            st.subheader("Resumo por Titular - Aquisição")
            if not d['df_titulares_aquisicao'].empty:
                df_aquisicao_display = d['df_titulares_aquisicao'].copy()
                
                # Adiciona linha de total
                total_row = pd.DataFrame([{
                    'TITULAR': 'TOTAL',
                    'PERCENTUAL': '',
                    'TOTAL CALCULADO': df_aquisicao_display['TOTAL CALCULADO'].sum()
                }])
                df_aquisicao_display = pd.concat([df_aquisicao_display, total_row], ignore_index=True)
                
                # Formata percentual
                df_aquisicao_display['PERCENTUAL'] = df_aquisicao_display['PERCENTUAL'].apply(
                    lambda x: f"{x:.1f}%" if isinstance(x, (int, float)) else x
                )
                
                # Aplica estilo - vermelho clarinho para linha TOTAL
                def highlight_total(row):
                    if row['TITULAR'] == 'TOTAL':
                        return ['background-color: #ffe6e6; font-weight: bold'] * len(row)
                    return [''] * len(row)
                
                st.dataframe(
                    df_aquisicao_display.style.format({
                        'TOTAL CALCULADO': format_currency
                    }).apply(highlight_total, axis=1),
                    hide_index=True,
                    use_container_width=True
                )
            
            st.subheader("Resumo por Titular - Administração")
            if not d['df_titulares_administracao'].empty:
                df_admin_display = d['df_titulares_administracao'].copy()
                
                # Adiciona linha de total
                total_row = pd.DataFrame([{
                    'TITULAR': 'TOTAL',
                    'PERCENTUAL': '',
                    'TOTAL CALCULADO': df_admin_display['TOTAL CALCULADO'].sum()
                }])
                df_admin_display = pd.concat([df_admin_display, total_row], ignore_index=True)
                
                # Formata percentual
                df_admin_display['PERCENTUAL'] = df_admin_display['PERCENTUAL'].apply(
                    lambda x: f"{x:.1f}%" if isinstance(x, (int, float)) else x
                )
                
                # Aplica estilo - vermelho clarinho para linha TOTAL
                def highlight_total(row):
                    if row['TITULAR'] == 'TOTAL':
                        return ['background-color: #ffe6e6; font-weight: bold'] * len(row)
                    return [''] * len(row)
                
                st.dataframe(
                    df_admin_display.style.format({
                        'TOTAL CALCULADO': format_currency
                    }).apply(highlight_total, axis=1),
                    hide_index=True,
                    use_container_width=True
                )
            
            st.subheader("Linhas de Incomes para Sistema Externo")
            if d['df_incomes_consolidado'] is not None:
                st.dataframe(
                    d['df_incomes_consolidado'],
                    hide_index=True,
                    use_container_width=True
                )
                
                # Validação das Incomes
                st.caption("🔍 Validação dos Valores")
                
                total_geral = d['total_geral']
                df_incomes = d['df_incomes_consolidado']
                
                # Check 1: Gross Amount bate com Total Geral
                gross_amount_income = df_incomes['Gross Amount'].iloc[0] if len(df_incomes) > 0 else 0
                check1 = round(gross_amount_income, 2) == round(total_geral, 2)
                
                # Check 2: Soma dos Net Amount bate com Gross Amount
                soma_net_amount = df_incomes['Net Amount (*)'].sum()
                check2 = round(soma_net_amount, 2) == round(gross_amount_income, 2)
                
                # Check 3: Splits batem com Net Amount
                check3_list = []
                for _, row in df_incomes.iterrows():
                    soma_splits = row['SPLIT AMOUNT | Organization (*)'] + row['SPLIT AMOUNT | Rights-Holder (*)']
                    net_amount = row['Net Amount (*)']
                    check3_list.append(round(soma_splits, 2) == round(net_amount, 2))
                check3 = all(check3_list)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        "Gross Amount = Total Geral",
                        "✅" if check1 else "❌",
                        f"{format_currency(gross_amount_income)} = {format_currency(total_geral)}"
                    )
                with col2:
                    st.metric(
                        "Soma Net Amount = Gross Amount",
                        "✅" if check2 else "❌",
                        f"{format_currency(soma_net_amount)}"
                    )
                with col3:
                    st.metric(
                        "Splits = Net Amount",
                        "✅" if check3 else "❌",
                        f"{len([x for x in check3_list if x])}/{len(check3_list)} linhas"
                    )
            
            st.divider()
            st.subheader("Detalhamento de Obras")
            
            status_filter_publisher = st.multiselect(
                "Filtrar por Status",
                options=['Y', 'N'],
                default=['Y', 'N'],
                format_func=lambda x: "Adquirida" if x == 'Y' else "Não Adquirida",
                key="status_filter_publisher"
            )
            
            # Se nenhum filtro for selecionado, mostra todas
            if not status_filter_publisher:
                status_filter_publisher = ['Y', 'N']
            
            df_obras_publisher_filtered = d['df_obras'][d['df_obras']['AQUIRED'].isin(status_filter_publisher)].copy()
            df_obras_publisher_filtered = df_obras_publisher_filtered.sort_values('TOTAL', ascending=False)
            
            st.dataframe(
                df_obras_publisher_filtered.style.format({
                    'TOTAL': format_currency
                }),
                hide_index=True,
                use_container_width=True
            )
        
        # Exportação de CSV com todas as incomes (Writer + Publisher)
        if dados['writer'] or dados['publisher']:
            st.divider()
            st.header("📥 Exportar Incomes Consolidadas")
            
            # Combina todas as incomes em um único DataFrame
            all_incomes = []
            
            if dados['writer'] and dados['writer']['df_incomes'] is not None:
                all_incomes.append(dados['writer']['df_incomes'])
            
            if dados['publisher'] and dados['publisher']['df_incomes_consolidado'] is not None:
                all_incomes.append(dados['publisher']['df_incomes_consolidado'])
            
            if all_incomes:
                df_all_incomes = pd.concat(all_incomes, ignore_index=True)
                
                # Salva o CSV usando BytesIO para evitar problemas de caminho
                from io import BytesIO
                csv_buffer = BytesIO()
                df_all_incomes.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                csv_bytes = csv_buffer.getvalue()
                
                st.success(f"✅ {len(df_all_incomes)} linhas de income consolidadas")
                
                # Botão de download
                st.download_button(
                    label="📥 Download CSV com as Incomes",
                    data=csv_bytes,
                    file_name="incomes_consolidadas.csv",
                    mime="text/csv"
                )
                
                # Mostra preview
                with st.expander("👁️ Visualizar todas as incomes"):
                    st.dataframe(df_all_incomes, hide_index=True, use_container_width=True)

if __name__ == "__main__":
    main()