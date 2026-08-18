"""Leitura do demonstrativo internacional da ABRAMUS em PDF.

Extraído de `views/abramus_int_to_excel.py` para ser reaproveitado por
qualquer página que precise do relatório Internacional sem depender de uma
conversão manual para Excel antes do upload.
"""

import re

import pandas as pd
import pdfplumber

_LINHAS_IGNORADAS = ('DISTRIBUIÇÃO DE DIREITOS', 'DATA :', 'TOTAL:', 'DEMONSTRATIVO', 'CPF:', 'ABRAMUS:', 'ECAD:')
_RE_ISWC = re.compile(r'(T\d{10})')
_RE_PERIODO = re.compile(r'\d{4}/\d{2}\s*-\s*\d{4}/\d{2}')


def ler_internacional(pdf_file) -> pd.DataFrame:
    """Extrai as linhas do demonstrativo internacional da ABRAMUS (PDF) para
    um DataFrame com colunas: Título, ISRC/ISWC, Sociedade, Território,
    Rubrica, Direito, Período, Rendimento."""
    data = []

    with pdfplumber.open(pdf_file) as pdf:
        current_title = None
        current_isrc = None

        for page in pdf.pages:
            text = page.extract_text()
            lines = text.split('\n')

            for line in lines:
                if any(x in line for x in _LINHAS_IGNORADAS):
                    continue

                # Detecta linha de título + ISRC
                isrc_match = _RE_ISWC.search(line)
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
                        period_match = _RE_PERIODO.search(line)
                        if not period_match:
                            continue
                        period = period_match.group(0)

                        # Posições fixas apenas para sociedade e território
                        society = parts[0]
                        territory = parts[1]

                        # Captura rubrica usando tudo que está entre território e período
                        period_start_index = line.find(period)
                        rubrica_text = line[len(society) + len(territory) + 2: period_start_index].strip()

                        data.append({
                            'Título': current_title,
                            'ISRC/ISWC': current_isrc,
                            'Sociedade': society,
                            'Território': territory,
                            'Rubrica': rubrica_text,
                            'Direito': 'AUTORAL',
                            'Período': period,
                            'Rendimento': value,
                        })
                    except Exception:
                        continue

    return pd.DataFrame(data)
