import streamlit as st
import pandas as pd
from typing import Dict, List
import plotly.express as px

# ---------------------------------
# Funções de formatação e extração de campos
# ---------------------------------

def formatar_percentual(valor_str: str) -> str:
    """Formata percentual no formato 9(03)V99 - 3 dígitos inteiros + 2 decimais"""
    if not valor_str or valor_str.strip() == '':
        return '0.00'
    
    valor_limpo = valor_str.strip()
    if len(valor_limpo) < 5:  # Deve ter pelo menos 5 dígitos (00000)
        valor_limpo = valor_limpo.zfill(5)
    
    # Últimos 2 dígitos são decimais
    parte_decimal = valor_limpo[-2:]
    # Primeiros dígitos são inteiros
    parte_inteira = valor_limpo[:-2]
    
    # Remove zeros à esquerda da parte inteira
    parte_inteira = parte_inteira.lstrip('0') or '0'
    
    return f"{parte_inteira}.{parte_decimal}"

def formatar_valor_numerico(valor_str: str) -> str:
    """Formata valores no formato 9(10)V999999999 - 10 dígitos inteiros + 9 decimais"""
    if not valor_str or valor_str.strip() == '':
        return '0.000000000'
    
    valor_limpo = valor_str.strip()
    if len(valor_limpo) < 19:  # Deve ter 19 dígitos
        valor_limpo = valor_limpo.zfill(19)
    
    # Últimos 9 dígitos são decimais
    parte_decimal = valor_limpo[-9:]
    # Primeiros 10 dígitos são inteiros
    parte_inteira = valor_limpo[:-9]
    
    # Remove zeros à esquerda da parte inteira
    parte_inteira = parte_inteira.lstrip('0') or '0'
    
    return f"{parte_inteira}.{parte_decimal}"

def formatar_mes_ano(data_str: str) -> str:
    """Formata data do formato MMAAAA para MM-AAAA"""
    if not data_str or data_str.strip() == '':
        return ''
    
    data_limpa = data_str.strip()
    if len(data_limpa) == 6:
        mes = data_limpa[:2]
        ano = data_limpa[2:]
        return f"{mes}-{ano}"
    return data_limpa

def formatar_periodo(periodo_str: str) -> str:
    """Formata período do formato DDMMAAAADDMMAAAA para DD-MM-AAAA DD-MM-AAAA"""
    if not periodo_str or periodo_str.strip() == '':
        return ''
    
    periodo_limpo = periodo_str.strip()
    if len(periodo_limpo) == 16:
        # Primeira data: primeiros 8 dígitos
        dia1 = periodo_limpo[:2]
        mes1 = periodo_limpo[2:4]
        ano1 = periodo_limpo[4:8]
        
        # Segunda data: últimos 8 dígitos
        dia2 = periodo_limpo[8:10]
        mes2 = periodo_limpo[10:12]
        ano2 = periodo_limpo[12:16]
        
        return f"{dia1}-{mes1}-{ano1} {dia2}-{mes2}-{ano2}"
    
    return periodo_limpo

def mapear_tipo_lancamento(codigo: str) -> str:
    """Mapeia código do tipo de lançamento para descrição"""
    mapeamento = {
        '1': 'Repasse',
        '2': 'Liberação Retido', 
        '3': 'Liberação Pendente',
        '4': 'Liberação Parâmetro',
        '5': 'Lançamento Manual'
    }
    return mapeamento.get(codigo.strip(), codigo.strip())

def extrair_campos_registro0(linha: str) -> Dict:
    """Extrai campos do REGISTRO '0' - HEADER"""
    campos = {}
    try:
        campos['NOM_TITULAR'] = linha[22:56].strip()
        campos['COD_TITULARECAD'] = linha[58:69].strip()
        campos['DAT_PAGAMENTO'] = formatar_mes_ano(linha[69:75].strip())
        campos['NOM_PSEUDOTITULAR'] = linha[75:109].strip()
    except IndexError:
        pass
    return campos

def extrair_campos_registro1(linha: str) -> Dict:
    """Extrai campos do REGISTRO '1' - AUDIOVISUAL/CINEMA"""
    campos = {}
    try:
        campos['DSC_RUBRICA'] = linha[4:49].strip()
        campos['TIT_OBRA'] = linha[49:109].strip()
        campos['COD_ECADOBRA'] = linha[109:122].strip()
        campos['NOM_TITULOORIG'] = linha[122:182].strip()
        campos['NOM_CAPITULOAUDIOORIG'] = linha[242:302].strip()
        campos['REFERENCIA'] = linha[362:397].strip()
        campos['PCT_PARTICIPACAO'] = linha[418:423].strip()
        campos['COD_CATEGORIA'] = linha[440:442].strip()
        campos['TIP_LANCAMENTO'] = mapear_tipo_lancamento(linha[442:443].strip())
        campos['ISWC'] = linha[450:461].strip()
        campos['ISRC'] = linha[461:473].strip()
        campos['NOM_INTERPRETE'] = linha[488:548].strip()
        campos['PERÍODO'] = formatar_periodo(linha[568:584].strip())
        campos['VLR_RENDOBRA'] = formatar_valor_numerico(linha[584:603].strip()) # Rendimento Total
        campos['PCT_PARTICIPACAO'] = formatar_percentual(linha[418:423].strip()) # Percentual do Titular
        campos['VLR_NOMINALTITOBRA'] = formatar_valor_numerico(linha[603:622].strip()) # Rateio
        campos['TIPO_REGISTRO'] = 'AUDIOVISUAL/CINEMA'
    except IndexError:
        pass
    return campos

def extrair_campos_registro2(linha: str) -> Dict:
    """Extrai campos do REGISTRO '2' - INDIRETA"""
    campos = {}
    try:
        campos['DSC_RUBRICA'] = linha[4:49].strip()
        campos['TIT_OBRA'] = linha[49:109].strip()
        campos['COD_ECADOBRA'] = linha[109:122].strip()
        campos['NOM_INTERPRETE'] = linha[122:182].strip()
        campos['REFERENCIA'] = linha[212:247].strip()
        campos['PCT_PARTICIPACAO'] = linha[268:273].strip()
        campos['COD_CATEGORIA'] = linha[290:292].strip()
        campos['TIP_LANCAMENTO'] = mapear_tipo_lancamento(linha[292:293].strip())
        campos['TOT_EXEC'] = linha[293:299].strip()
        campos['ISWC'] = linha[300:311].strip()
        campos['ISRC'] = linha[311:323].strip()
        campos['IND_LANCAMENTO'] = linha[330:331].strip()
        campos['PERÍODO'] = formatar_periodo(linha[367:383].strip())
        campos['VLR_RENDOBRA'] = formatar_valor_numerico(linha[383:402].strip()) # Rendimento Total
        campos['PCT_PARTICIPACAO'] = formatar_percentual(linha[268:273].strip()) # Percentual do Titular
        campos['VLR_NOMINALTITOBRA'] = formatar_valor_numerico(linha[402:421].strip()) # Rateio
        campos['TIPO_REGISTRO'] = 'INDIRETA'
    except IndexError:
        pass
    return campos

def extrair_campos_registro3(linha: str) -> Dict:
    """Extrai campos do REGISTRO '3' - SHOW"""
    campos = {}
    try:
        campos['DSC_RUBRICA'] = linha[4:49].strip()
        campos['TIT_OBRA'] = linha[49:109].strip()
        campos['COD_ECADOBRA'] = linha[109:122].strip()
        campos['REFERENCIA'] = linha[122:157].strip()
        campos['DSC_TITULOFUNCAO'] = linha[166:216].strip()
        campos['DAT_PERIODO'] = formatar_periodo(linha[216:232].strip())
        campos['NOM_INTERPRETESHOW'] = linha[232:282].strip()
        campos['DSC_LOCAL'] = linha[282:312].strip()
        campos['NOM_MUNICIPIOSHOW'] = linha[312:332].strip()
        campos['PCT_PARTICIPACAO'] = linha[346:351].strip()
        campos['TIP_LANCAMENTO'] = mapear_tipo_lancamento(linha[370:371].strip())
        campos['TOT_EXEC'] = linha[371:377].strip()
        campos['ISWC'] = linha[378:389].strip()
        campos['VLR_RENDOBRA'] = formatar_valor_numerico(linha[420:439].strip()) # Rendimento Total
        campos['PCT_PARTICIPACAO'] = formatar_percentual(linha[346:351].strip()) # Percentual do Titular
        campos['VLR_NOMINALTITOBRA'] = formatar_valor_numerico(linha[439:458].strip()) # Rateio
        campos['TIPO_REGISTRO'] = 'SHOW'
    except IndexError:
        pass
    return campos

# ---------------------------------
# Função principal para processar múltiplos arquivos TXT
# ---------------------------------

def processar_multiplos_arquivos_txt(arquivos_txt) -> pd.DataFrame:
    """
    Processa múltiplos arquivos TXT e retorna um DataFrame único consolidado
    """
    header_info = {}
    todos_registros = []
    
    # Processa cada arquivo
    for arquivo_txt in arquivos_txt:
        #st.write(f"📁 Processando: {arquivo_txt.name}")
        
        # Lê o conteúdo do arquivo
        conteudo = arquivo_txt.read()
        
        # Decodifica se necessário
        if isinstance(conteudo, bytes):
            try:
                conteudo = conteudo.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    conteudo = conteudo.decode('latin1')
                except UnicodeDecodeError:
                    conteudo = conteudo.decode('cp1252')
        
        # Processa linha por linha
        for num_linha, linha in enumerate(conteudo.split('\n'), 1):
            linha = linha.rstrip()
            
            if linha and len(linha) > 0:
                primeiro_digito = linha[0]
                
                if primeiro_digito == '0':
                    header_info = extrair_campos_registro0(linha)
                    
                elif primeiro_digito == '1':
                    campos = extrair_campos_registro1(linha)
                    todos_registros.append(campos)
                    
                elif primeiro_digito == '2':
                    campos = extrair_campos_registro2(linha)
                    todos_registros.append(campos)
                    
                elif primeiro_digito == '3':
                    campos = extrair_campos_registro3(linha)
                    todos_registros.append(campos)
    
    # Cria DataFrame consolidado (resto do código permanece igual)
    if todos_registros:
        df_final = pd.DataFrame(todos_registros)
        
        # Adiciona informações do header em todas as linhas
        for campo, valor in header_info.items():
            df_final[campo] = valor
        
        # Renomeia as colunas conforme especificado
        mapeamento_colunas = {
            'NOM_TITULAR' : 'TITULAR',
            'COD_TITULARECAD' : 'COD ECAD TITULAR',
            'DAT_PAGAMENTO' : 'MES REPASSE',
            'NOM_PSEUDOTITULAR' : 'PSEUDONIMO TITULAR',
            'DSC_RUBRICA': 'RUBRICA',
            'TIT_OBRA': 'TITULO DA MUSICA',
            'COD_ECADOBRA': 'COD ECAD MUSICA',
            'NOM_TITULOORIG': 'TITULO AUDIOVISUAL',
            'NOM_CAPITULOAUDIOORIG': 'CAPITULO AUDIOVISUAL',
            'REFERENCIA': 'REFERENCIA AUTORAL',
            'VLR_RENDOBRA': 'VALOR TOTAL',
            'PCT_PARTICIPACAO': 'PERC TITULAR',
            'VLR_NOMINALTITOBRA': 'RATEIO',
            'COD_CATEGORIA': 'CAT',
            'TIP_LANCAMENTO': 'TIPO DISTRIBUICAO',
            'ISWC': 'ISWC',
            'ISRC': 'ISRC',
            'NOM_INTERPRETE': 'INTERPRETE',
            'PERÍODO': 'PERIODO DISTRIBUICAO',
            'TOT_EXEC': 'EXECUCOES',
            'IND_LANCAMENTO': 'TIPO LANCAMENTO',
            'DSC_TITULOFUNCAO': 'NOME SHOW',
            'DAT_PERIODO': 'PERIODO SHOW',
            'NOM_INTERPRETESHOW': 'INTERPRETE SHOW',
            'DSC_LOCAL': 'LOCAL SHOW',
            'NOM_MUNICIPIOSHOW': 'CIDADE SHOW'
        }
        
        df_final = df_final.rename(columns=mapeamento_colunas)

        # Define a ordem das colunas
        ordem_colunas = [
            'MES REPASSE',
            'TITULAR',
            'PSEUDONIMO TITULAR',
            'COD ECAD TITULAR',
            'TIPO_REGISTRO',
            'CAT',
            'TITULO DA MUSICA',
            'COD ECAD MUSICA',
            'REFERENCIA AUTORAL',
            'INTERPRETE',
            'ISWC',
            'ISRC',
            'RUBRICA',
            'TIPO DISTRIBUICAO',
            'EXECUCOES',
            'VALOR TOTAL',
            'PERC TITULAR',
            'RATEIO',
            'TITULO AUDIOVISUAL',
            'CAPITULO AUDIOVISUAL',
            'PERIODO DISTRIBUICAO',
            'TIPO LANCAMENTO',
            'NOME SHOW',
            'PERIODO SHOW',
            'INTERPRETE SHOW',
            'LOCAL SHOW',
            'CIDADE SHOW'

        ]

        # Reordena as colunas (só inclui colunas que existem no DataFrame)
        colunas_existentes = [col for col in ordem_colunas if col in df_final.columns]
        df_final = df_final[colunas_existentes]

        return df_final
    else:
        return pd.DataFrame()

# ---------------------------------
# Função principal do Streamlit
# ---------------------------------

def main():
    st.set_page_config(
        page_title="CONVERSOR TXT ECAD",
        layout="wide"
    )
    
    st.title("CONVERSOR TXT ECAD")
    st.divider()
    
     
    # Upload do arquivo
    arquivos_uploadados = st.file_uploader(
        "Selecione o arquivo TXT",
        type=['txt'],
        accept_multiple_files=True,
        help="Faça upload do arquivo TXT para conversão"
    )
    
    if arquivos_uploadados is not None:
        try:
            # Processa o arquivo
            with st.spinner("Processando arquivo..."):
                df_consolidado = processar_multiplos_arquivos_txt(arquivos_uploadados)
            
            st.divider()
            
            # Informações do Header (se disponível)
            if 'TITULAR' in df_consolidado.columns:
                st.markdown("### ℹ️ Informações do Titular")
                col1, col2 = st.columns(2)
                
                with col1:
                    if df_consolidado['TITULAR'].iloc[0]:
                        st.write("**Titular:** ", df_consolidado['TITULAR'].iloc[0])
                    if 'MES REPASSE' in df_consolidado.columns and df_consolidado['MES REPASSE'].iloc[0]:
                        st.write("**Mês Repasse:** ", df_consolidado['MES REPASSE'].iloc[0])
                
                with col2:
                    if 'COD ECAD TITULAR' in df_consolidado.columns and df_consolidado['COD ECAD TITULAR'].iloc[0]:
                        st.write("**Código ECAD:** ", df_consolidado['COD ECAD TITULAR'].iloc[0])
                    if 'PSEUDONIMO TITULAR' in df_consolidado.columns and df_consolidado['PSEUDONIMO TITULAR'].iloc[0]:
                        st.write("**Pseudônimo:** ", df_consolidado['PSEUDONIMO TITULAR'].iloc[0])
            
            st.divider()

            if not df_consolidado.empty:
                # Estatísticas melhoradas
               
                # Contagem por tipo de registro
                contagem_tipos = df_consolidado['TIPO_REGISTRO'].value_counts()
                
                # Cálculos financeiros
                valor_total_soma = df_consolidado['VALOR TOTAL'].astype(str).str.replace(',', '.').astype(float).sum()
                rateio_soma = df_consolidado['RATEIO'].astype(str).str.replace(',', '.').astype(float).sum()
                
                # Container principal com fundo
                with st.container():
                    st.markdown("""
                    <style>
                    .metric-container {
                        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                        padding: 1rem;
                        border-radius: 10px;
                        margin: 1rem 0;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                                       
                    # Segunda linha - Valores financeiros
                    st.markdown("#### 💰 Resumo Financeiro")
                    col5, col6, col7 = st.columns(3)
                    
                    with col5:
                        st.metric(
                            label="Valor Total",
                            value=f"R$ {valor_total_soma:,.2f}",
                            help="Soma de todos os valores totais dos registros"
                        )
                        
                    with col6:
                        st.metric(
                            label="Rateio do Titular",
                            value=f"R$ {rateio_soma:,.2f}",
                            help="Soma de todos os rateios destinados ao titular"
                        )
                        
                    with col7:
                        if 'MES REPASSE' in df_consolidado.columns and df_consolidado['MES REPASSE'].iloc[0]:
                            mes_repasse = df_consolidado['MES REPASSE'].iloc[0]
                            st.metric(
                                label="Período de Repasse",
                                value=mes_repasse,
                                help="Mês/ano do repasse processado"
                            )
                        else:
                            st.metric(label="📅 Período", value="N/A")

                    st.divider()
                    
                    # Gráfico de pizza dos tipos de registro
                    if len(contagem_tipos) > 0:
                        st.markdown("#### 📊 Distribuição por Tipo de Registro")
                        
                        
                        fig = px.pie(
                            values=contagem_tipos.values, 
                            names=contagem_tipos.index,
                            color_discrete_sequence=['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
                        )
                        fig.update_traces(textposition='inside', textinfo='percent+label')
                        fig.update_layout(showlegend=True, height=400)
                        st.plotly_chart(fig, use_container_width=True)

                st.divider()
                
                # Visualização da planilha única consolidada
                st.subheader("📋 Planilha Consolidada")
                st.dataframe(df_consolidado, use_container_width=True, hide_index=True)
                
                
                
                # Download da planilha única
                st.subheader("📥 Download da Planilha")
                csv_consolidado = df_consolidado.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="⬇️ Download CSV Consolidado",
                    data=csv_consolidado,
                    file_name="registros_consolidados.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
            else:
                st.warning("Nenhum registro válido encontrado no arquivo.")
                        
        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {str(e)}")
            st.exception(e)
    
    else:
        st.info("👆 Faça upload de um arquivo TXT para começar a conversão.")
    
    # Rodapé
    st.divider()
    st.markdown(
        """
        <div style='text-align: center; color: gray;'>
        Conversor TXT para CSV
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()