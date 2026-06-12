"""
Gerador do seed de regras do Direct Incomes (data/direct_incomes/regras.json).

Recebe o dicionário REGRAS exatamente como está no notebook original
(regras-distribuicao.ipynb) e converte para o schema JSON usado pela página
do lyra (pages/19_19_Direct_Incomes.py).

Schema de saída:
{
  "periodo": "2025Q4",
  "regras": [
    {
      "catalogo": "ZEIDER",
      "fonte": "UNIVERSAL MUSIC",
      "historico": null,                # opcional (string ou null)
      "money_in": "UNIVERSAL MUSIC LTDA",
      "incomes": [
        {"descricao": "UNIVERSAL MUSIC - ZEIDER - NN AQUISICAO (50%)",
         "money_out": "NAS NUVENS (ZEIDER) (LS - 50%)",
         "org_pct": 0, "rights_pct": 66.67},
        ...
      ]
    },
    ...
  ]
}

O "periodo" deixa de ser concatenado no nome (como no notebook) e passa a ser
um prefixo aplicado em tempo de cálculo. Por isso guardamos só a "descricao"
(o sufixo, sem o período). Rode uma vez para (re)gerar o JSON:

    python froozen/_gen_direct_incomes_rules.py
"""

import json
from pathlib import Path

PERIODO = "2025Q4"

REGRAS = {

    #-------------------------------------------------
    # BETO CORREA
    #-------------------------------------------------
    ("BETO CORREA", "SOCINPRO"): [
        {"Contract - Money In": "SOCINPRO"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - BETO CORREA - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - BETO CORREA - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (BETO CORREA) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "BETO CORREA (BETO CORREA) (BC PRODUCAO) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 10,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],
    ("BETO CORREA", "UNIVERSAL MUSIC PUBLISHING"): [
        {"Contract - Money In": "UNIVERSAL MUSIC PUBLISHING"},
        {"nome_income1": PERIODO + " UMPG - BETO CORREA - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " UMPG - BETO CORREA - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (BETO CORREA) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "BETO CORREA (BETO CORREA) (BC PRODUCAO) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 10,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],
    ("BETO CORREA", "NOSSA MUSICA"): [
        {"Contract - Money In": "NOSSA MUSICA"},
        {"nome_income1": PERIODO + " NOSSA MUSICA - BETO CORREA - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " NOSSA MUSICA - BETO CORREA - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (BETO CORREA) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "BETO CORREA (BETO CORREA) (BC PRODUCAO) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 10,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],

    #-------------------------------------------------
    # TICO SANTA CRUZ
    #-------------------------------------------------
    ("TICO SANTA CRUZ", "UBC"): [
        {"Contract - Money In": "UBC"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - TICO SANTA CRUZ / OUTRO LUGAR - NN AQUISICAO (77,5%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - TICO SANTA CRUZ / OUTRO LUGAR - RECUPERAVEL (22,5%)"},
        {"Contract - Money Out": "NAS NUVENS (TICO SANTA CRUZ) (PS - 77,5%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 77.5},
        {"Contract - Money Out": "TICO SANTA CRUZ (TICO SANTA CRUZ) (OUTRO LUGAR) (PS - 22,5%)",
            "SPLIT AMOUNT | Organization (%)": 10,
            "SPLIT AMOUNT | Rights-Holder (%)": 12.5},
    ],
    ("TICO SANTA CRUZ", "WARNER CHAPPELL"): [
        {"Contract - Money In": "WARNER CHAPPELL"},
        {"nome_income1": PERIODO + " WARNER CHAPPELL - TICO SANTA CRUZ / OUTRO LUGAR - NN AQUISICAO (77,5%)"},
        {"nome_income2": PERIODO + " WARNER CHAPPELL - TICO SANTA CRUZ / OUTRO LUGAR - RECUPERAVEL (22,5%)"},
        {"Contract - Money Out": "NAS NUVENS (TICO SANTA CRUZ) (PS - 77,5%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 77.5},
        {"Contract - Money Out": "TICO SANTA CRUZ (TICO SANTA CRUZ) (OUTRO LUGAR) (PS - 22,5%)",
            "SPLIT AMOUNT | Organization (%)": 10,
            "SPLIT AMOUNT | Rights-Holder (%)": 12.5},
    ],

    #-------------------------------------------------
    #  ACCIOLY
    #-------------------------------------------------
    ("ACCIOLY", "UBC", "REPASSE - Lalu"): [
        {"Contract - Money In": "UBC"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - ACCIOLY EDITORA - NN AQUISICAO (50%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - ACCIOLY EDITORA - REPASSE (50%)"},
        {"Contract - Money Out": "NAS NUVENS (ACCIOLY / LALU) (PS - 12,5%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 50},
        {"Contract - Money Out": "ACCIOLY EDITORA (ACCIOLY) (PS - 12,5%)",
            "SPLIT AMOUNT | Organization (%)": 30,
            "SPLIT AMOUNT | Rights-Holder (%)": 20},
    ],
    ("ACCIOLY", "UBC", "ADMINISTRACAO LALU EDICOES"): [
        {"Contract - Money In": "UBC"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - ACCIOLY EDITORA - NN AQUISICAO (50%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - ACCIOLY EDITORA - REPASSE (50%)"},
        {"Contract - Money Out": "NAS NUVENS (ACCIOLY / LALU) (PS - 12,5%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 50},
        {"Contract - Money Out": "ACCIOLY EDITORA (ACCIOLY) (PS - 12,5%)",
            "SPLIT AMOUNT | Organization (%)": 30,
            "SPLIT AMOUNT | Rights-Holder (%)": 20},
    ],
    ("ACCIOLY", "POLY SOM COMERCIO E INDUSTRIA"): [
        {"Contract - Money In": "SOMAX"},
        {"nome_income1": PERIODO + " POLYSOM - ACCIOLY EDITORA - NN AQUISICAO (50%)"},
        {"nome_income2": PERIODO + " POLYSOM - ACCIOLY EDITORA - REPASSE (50%)"},
        {"Contract - Money Out": "NAS NUVENS (ACCIOLY NETO) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 50},
        {"Contract - Money Out": "ACCIOLY NETO (ACCIOLY EDITORA) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 50},
    ],

    #-------------------------------------------------
    # CARLINHOS BROWN
    #-------------------------------------------------
    ("CARLINHOS BROWN", "ADA"): [
        {"Contract - Money In": "ADA"},
        {"nome_income1": PERIODO + " ADA - CARLINHOS BROWN / CANDYALL - NN AQUISICAO (75%)"},
        {"nome_income2": PERIODO + " ADA - CARLINHOS BROWN / CANDYALL - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (CARLINHOS BROWN / CANDYALL) (LS - 75%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 75},
        {"Contract - Money Out": "CANDYALL (CARLINHOS BROWN) (LS - 25%)",
            "SPLIT AMOUNT | Organization (%)": 15,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],
    ("CARLINHOS BROWN", "UBC"): [
        {"Contract - Money In": "UBC"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - CARLINHOS BROWN / CANDYALL - NN AQUISICAO (75%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - CARLINHOS BROWN / CANDYALL - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (CARLINHOS BROWN / CANDYALL) (PS - 75%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 75},
        {"Contract - Money Out": "CANDYALL (CARLINHOS BROWN) (PS - 25%)",
            "SPLIT AMOUNT | Organization (%)": 15,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],
    ("CARLINHOS BROWN", "MEDIA IP RIGHTS"): [
        {"Contract - Money In": "MEDIA IP RIGHTS"},
        {"nome_income1": PERIODO + "CONEXOS INTERNACIONAIS - CARLINHOS BROWN / CANDYALL - NN AQUISICAO (75%)"},
        {"nome_income2": PERIODO + "CONEXOS INTERNACIONAIS - CARLINHOS BROWN / CANDYALL - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (CARLINHOS BROWN / CANDYALL) (LS - 75%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 75},
        {"Contract - Money Out": "CANDYALL (CARLINHOS BROWN) (LS - 25%)",
            "SPLIT AMOUNT | Organization (%)": 15,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],
    ("CARLINHOS BROWN", "MONTE CRIACAO"): [
        {"Contract - Money In": "MONTE CRIACAO"},
        {"nome_income1": PERIODO + " MONTE CRIACAO - CARLINHOS BROWN / CANDYALL - NN AQUISICAO (75%)"},
        {"nome_income2": PERIODO + " MONTE CRIACAO - CARLINHOS BROWN / CANDYALL - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (CARLINHOS BROWN / CANDYALL) (LS - 75%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 75},
        {"Contract - Money Out": "CANDYALL (CARLINHOS BROWN) (LS - 25%)",
            "SPLIT AMOUNT | Organization (%)": 15,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],
    ("CARLINHOS BROWN", "SACEM"): [
        {"Contract - Money In": "SACEM"},
        {"nome_income1": PERIODO + " SACEM - CARLINHOS BROWN / CANDYALL - NN AQUISICAO (75%)"},
        {"nome_income2": PERIODO + " SACEM - CARLINHOS BROWN / CANDYALL - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (CARLINHOS BROWN / CANDYALL) (LS - 75%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 75},
        {"Contract - Money Out": "CANDYALL (CARLINHOS BROWN) (LS - 25%)",
            "SPLIT AMOUNT | Organization (%)": 15,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],
    ("CARLINHOS BROWN", "UNIVERSAL MUSIC"): [
        {"Contract - Money In": "UNIVERSAL MUSIC"},
        {"nome_income1": PERIODO + " UNIVERSAL MUSIC - CARLINHOS BROWN / CANDYALL - NN AQUISICAO (75%)"},
        {"nome_income2": PERIODO + " UNIVERSAL MUSIC - CARLINHOS BROWN / CANDYALL - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (CARLINHOS BROWN / CANDYALL) (LS - 75%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 75},
        {"Contract - Money Out": "CANDYALL (CARLINHOS BROWN) (LS - 25%)",
            "SPLIT AMOUNT | Organization (%)": 15,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],

    #-------------------------------------------------
    # LAZAO
    #-------------------------------------------------
    ("LAZAO", "ABRAMUS", "TRANSFERIDO DE POP MUNDI PRODUCOES ARTISTICAS LTDA"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - POP MUNDI - NN AQUISICAO (50%)"},
        {"Contract - Money Out": "NAS NUVENS (PS) - LAZAO (12,5%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 100},
    ],
    ("LAZAO", "ABRAMUS", "VENDA CATALOGO - CESSAO - POP MUNDI PRODUCOES ARTISTICAS LTDA"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - POP MUNDI - RECUPERAVEL (50%)"},
        {"Contract - Money Out": "POP MUNDI - LAZAO (12,5%)",
            "SPLIT AMOUNT | Organization (%)": 60,
            "SPLIT AMOUNT | Rights-Holder (%)": 40},
    ],

    #-------------------------------------------------
    # CELSO FONSECA
    #-------------------------------------------------
    ("CELSO FONSECA", "UBC", "ADMINISTRACAO CELSO JOSE DA FONSECA"): [
        {"Contract - Money In": "UBC"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - CELSO FONSECA - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - CELSO FONSECA - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (CELSO FONSECA) (PS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "CELSO FONSECA (CELSO FONSECA) (POLAROIDES) (PS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 5,
            "SPLIT AMOUNT | Rights-Holder (%)": 15},
    ],
    ("CELSO FONSECA", "UBC"): [
        {"Contract - Money In": "UBC"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - CELSO FONSECA + POLAROIDES - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - CELSO FONSECA + POLAROIDES - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (CELSO FONSECA) (PS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "CELSO FONSECA (CELSO FONSECA) (POLAROIDES) (PS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 5,
            "SPLIT AMOUNT | Rights-Holder (%)": 15},
    ],
    ("CELSO FONSECA", "UBC", "REPASSE CELSO FONSECA"): [
        {"Contract - Money In": "UBC"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - POLAROIDES (PF) - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - POLAROIDES (PF) - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (CELSO FONSECA) (PS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "CELSO FONSECA (CELSO FONSECA) (POLAROIDES) (PS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 5,
            "SPLIT AMOUNT | Rights-Holder (%)": 15},
    ],
    ("CELSO FONSECA", "COSTA & VALLE"): [
        {"Contract - Money In": "COSTA & VALLE"},
        {"nome_income1": PERIODO + " CONEXOS INTERNACIONAIS - CELSO FONSECA / POLAROIDES - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " CONEXOS INTERNACIONAIS - CELSO FONSECA / POLAROIDES - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (CELSO FONSECA) (PS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "CELSO FONSECA (CELSO FONSECA) (POLAROIDES) (PS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 5,
            "SPLIT AMOUNT | Rights-Holder (%)": 15},
    ],
    ("CELSO FONSECA", "DUBAS"): [
        {"Contract - Money In": "DUBAS"},
        {"nome_income1": PERIODO + " DUBAS - CELSO FONSECA / POLAROIDES - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " DUBAS - CELSO FONSECA / POLAROIDES - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (CELSO FONSECA) (PS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "CELSO FONSECA (CELSO FONSECA) (POLAROIDES) (PS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 5,
            "SPLIT AMOUNT | Rights-Holder (%)": 15},
    ],
    ("CELSO FONSECA", "WARNER CHAPPELL"): [
        {"Contract - Money In": "WARNER CHAPPELL"},
        {"nome_income1": PERIODO + " WARNER CHAPPELL - CELSO FONSECA - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " WARNER CHAPPELL - CELSO FONSECA - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (CELSO FONSECA) (PS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "CELSO FONSECA (CELSO FONSECA) (POLAROIDES) (PS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 5,
            "SPLIT AMOUNT | Rights-Holder (%)": 15},
    ],
    ("CELSO FONSECA", "SACEM"): [
        {"Contract - Money In": "SACEM"},
        {"nome_income1": PERIODO + " SACEM - CELSO FONSECA - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " SACEM - CELSO FONSECA - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (CELSO FONSECA) (PS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "CELSO FONSECA (CELSO FONSECA) (POLAROIDES) (PS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 5,
            "SPLIT AMOUNT | Rights-Holder (%)": 15},
    ],

    #-------------------------------------------------
    # BETO JAMAICA
    #-------------------------------------------------
    ("BETO JAMAICA", "ABRAMUS"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - BETO JAMAICA - NN AQUISICAO (50%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - BETO JAMAICA - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (BETO JAMAICA) (WS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 66.67},
        {"Contract - Money Out": "BETO JAMAICA (BETO JAMAICA / RECOUP) (WS - 25%)",
            "SPLIT AMOUNT | Organization (%)": 6.66,
            "SPLIT AMOUNT | Rights-Holder (%)": 26.67},
    ],
    ("BETO JAMAICA", "WARNER CHAPPELL"): [
        {"Contract - Money In": "WARNER CHAPPELL"},
        {"nome_income1": PERIODO + " WARNER CHAPPELL - BETO JAMAICA - NN AQUISICAO (50%)"},
        {"nome_income2": PERIODO + " WARNER CHAPPELL - BETO JAMAICA - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (BETO JAMAICA) (WS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 66.67},
        {"Contract - Money Out": "BETO JAMAICA (BETO JAMAICA / RECOUP) (WS - 25%)",
            "SPLIT AMOUNT | Organization (%)": 6.66,
            "SPLIT AMOUNT | Rights-Holder (%)": 26.67},
    ],

    #-------------------------------------------------
    # VINICIUS JUNQUEIRA
    #-------------------------------------------------
    ("VINICIUS JUNQUEIRA", "ABRAMUS"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - VINICIUS JUNQUEIRA - NN AQUISICAO (30%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - VINICIUS JUNQUEIRA - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (VINICIUS JUNQUEIRA) (WS - 30%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 60},
        {"Contract - Money Out": "VINICIUS JUNQUEIRA (VINICIUS JUNQUEIRA / RECOUP) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 40},
    ],

    #-------------------------------------------------
    # LUIZA POSSI
    #-------------------------------------------------
    ("LUIZA POSSI", "ABRAMUS", "VENDA CATALOGO - CESSAO - LUIZA POSSI GADELHA"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - LUIZA POSSI - NN AQUISICAO (80%)"},
        {"Contract - Money Out": "NAS NUVENS (LUIZA POSSI) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 100},
    ],
    ("LUIZA POSSI", "ABRAMUS", "VENDA CATALOGO - CESSAO - HELENA PRODUCOES ARTISTICAS LTDA ME"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - LUIZA POSSI (HELENA) - NN AQUISICAO (80%)"},
        {"Contract - Money Out": "NAS NUVENS (LUIZA POSSI) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 100},
    ],
    ("LUIZA POSSI", "ABRAMUS", "TRANSFERIDO DE LUIZA POSSI GADELHA"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - LUIZA POSSI - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "LUIZA POSSI (LUIZA POSSI) (HELENA PRODUCOES) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 50,
            "SPLIT AMOUNT | Rights-Holder (%)": 50},
    ],
    ("LUIZA POSSI", "ABRAMUS", "TRANSFERIDO DE HELENA"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - LUIZA POSSI (HELENA) - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "LUIZA POSSI (LUIZA POSSI) (HELENA PRODUCOES) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 50,
            "SPLIT AMOUNT | Rights-Holder (%)": 50},
    ],
    ("LUIZA POSSI", "WARNER CHAPPELL"): [
        {"Contract - Money In": "WARNER CHAPPELL"},
        {"nome_income1": PERIODO + " WARNER CHAPPELL - LUIZA POSSI - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " WARNER CHAPPELL - LUIZA POSSI - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (LUIZA POSSI) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "LUIZA POSSI (LUIZA POSSI) (HELENA PRODUCOES) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 10,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],
    ("LUIZA POSSI", "INDIE RECORDS"): [
        {"Contract - Money In": "INDIE RECORDS"},
        {"nome_income1": PERIODO + " INDIE RECORDS - LUIZA POSSI - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " INDIE RECORDS - LUIZA POSSI - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (LUIZA POSSI) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "LUIZA POSSI (LUIZA POSSI) (HELENA PRODUCOES) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 10,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],
    ("LUIZA POSSI", "UNIVERSAL MUSIC"): [
        {"Contract - Money In": "UNIVERSAL MUSIC LTDA"},
        {"nome_income1": PERIODO + " UNIVERSAL MUSIC - LUIZA POSSI - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " UNIVERSAL MUSIC - LUIZA POSSI - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (LUIZA POSSI) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "LUIZA POSSI (LUIZA POSSI) (HELENA PRODUCOES) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 10,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],

    #-------------------------------------------------
    # ZEIDER
    #-------------------------------------------------
    ("ZEIDER", "ABRAMUS", "VENDA CATALOGO - CESSAO - ZEIDER FERNANDO PIRES"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - ZEIDER - NN AQUISICAO (50%)"},
        {"Contract - Money Out": "NAS NUVENS (ZEIDER) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 100},
    ],
    ("ZEIDER", "ABRAMUS", "TRANSFERIDO DE ZEIDER FERNANDO PIRES"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - ZEIDER - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "ZEIDER (ZEIDER) (Z PRODUCOES / RECOUP) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 100},
    ],
    ("ZEIDER", "ABRAMUS", "VENDA CATALOGO - CESSAO - Z PRODUCOES ARTISTICAS LTDA - ME"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - Z PROD - NN AQUISICAO (50%)"},
        {"Contract - Money Out": "NAS NUVENS (ZEIDER) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 100},
    ],
    ("ZEIDER", "ABRAMUS", "TRANSFERIDO DE Z PRODUCOES ARTISTICAS LTDA - ME"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - Z PROD - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "ZEIDER (ZEIDER) (Z PRODUCOES / RECOUP) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 100},
    ],
    ("ZEIDER", "UNIVERSAL MUSIC"): [
        {"Contract - Money In": "UNIVERSAL MUSIC LTDA"},
        {"nome_income1": PERIODO + " UNIVERSAL MUSIC - ZEIDER - NN AQUISICAO (50%)"},
        {"nome_income2": PERIODO + " UNIVERSAL MUSIC - ZEIDER - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (ZEIDER) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 66.67},
        {"Contract - Money Out": "ZEIDER (ZEIDER) (Z PRODUCOES / RECOUP) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 33.33},
    ],
    ("ZEIDER", "UNIVERSAL MUSIC PUBLISHING"): [
        {"Contract - Money In": "UNIVERSAL MUSIC PUBLISHING"},
        {"nome_income1": PERIODO + " UNIVERSAL MUSIC PUBLISHING - ZEIDER - NN AQUISICAO (50%)"},
        {"nome_income2": PERIODO + " UNIVERSAL MUSIC PUBLISHING - ZEIDER - RECUPERAVEL (25%)"},
        {"Contract - Money Out": "NAS NUVENS (ZEIDER) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 66.67},
        {"Contract - Money Out": "ZEIDER (ZEIDER) (Z PRODUCOES / RECOUP) (LS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 33.33},
    ],

    #-------------------------------------------------
    # ALBERTO ROSENBLIT
    #-------------------------------------------------
    ("ROSENBLIT", "UBC"): [
        {"Contract - Money In": "UBC"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - ROSENBLIT - NN AQUISICAO (55%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - ROSENBLIT - RECUPERAVEL (35%)"},
        {"nome_income3": PERIODO + " EXECUCAO PUBLICA - ROSENBLIT - ORB MUSIC FEE (10%)"},
        {"Contract - Money Out": "NAS NUVENS (ROSENBLIT) (WS - 55%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 55},
        {"Contract - Money Out": "ALBERTO ROSENBLIT (ROSENBLIT / RECOUP) (WS - 35%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 35},
        {"Contract - Money Out": "ORB MUSIC (ROSENBLIT) (FEE) (WS - 10%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 10},
    ],

    #-------------------------------------------------
    # DADI
    #-------------------------------------------------
    ("DADI", "ABRAMUS"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - DADI - NN AQUISICAO (70%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - DADI - RECUPERAVEL (30%)"},
        {"Contract - Money Out": "NAS NUVENS (DADI) (WS - 70%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 70},
        {"Contract - Money Out": "DADI (DADI/ RECOUP) (WS - 30%)",
            "SPLIT AMOUNT | Organization (%)": 15,
            "SPLIT AMOUNT | Rights-Holder (%)": 15},
    ],

    #-------------------------------------------------
    # ANDRE MORAES
    #-------------------------------------------------
    ("ANDRE MORAES", "SOCINPRO"): [
        {"Contract - Money In": "SOCINPRO"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - ANDRE MORAES - NN AQUISICAO (50%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - ANDRE MORAES - RECUPERAVEL (50%)"},
        {"Contract - Money Out": "NAS NUVENS (ANDRE MORAES) (WS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 50},
        {"Contract - Money Out": "ANDRE MORAES (ANDRE MORAES/ RECOUP) (WS - 50%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 50},
    ],

    #-------------------------------------------------
    # PROJOTA
    #-------------------------------------------------
    ("PROJOTA", "ABRAMUS"): [
        {"Contract - Money In": "ABRAMUS"},
        {"nome_income1": PERIODO + " EXECUCAO PUBLICA - PROJOTA - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " EXECUCAO PUBLICA - PROJOTA - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (PROJOTA) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "PROJOTA (PROJOTA) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 4,
            "SPLIT AMOUNT | Rights-Holder (%)": 16},
    ],
    ("PROJOTA", "UNIVERSAL MUSIC PUBLISHING"): [
        {"Contract - Money In": "UNIVERSAL MUSIC PUBLISHING"},
        {"nome_income1": PERIODO + " UNIVERSAL MUSIC PUBLISHING - PROJOTA - NN AQUISICAO (80%)"},
        {"nome_income2": PERIODO + " UNIVERSAL MUSIC PUBLISHING - PROJOTA - RECUPERAVEL (20%)"},
        {"Contract - Money Out": "NAS NUVENS (PROJOTA) (WS - 80%)",
            "SPLIT AMOUNT | Organization (%)": 0,
            "SPLIT AMOUNT | Rights-Holder (%)": 80},
        {"Contract - Money Out": "PROJOTA (PROJOTA) (WS - 20%)",
            "SPLIT AMOUNT | Organization (%)": 4,
            "SPLIT AMOUNT | Rights-Holder (%)": 16},
    ],

}


def parse_rule(value):
    """Converte uma entrada do REGRAS no formato do notebook para o schema novo."""
    money_in = None
    nomes = []
    splits = []
    for d in value:
        if "Contract - Money In" in d:
            money_in = d["Contract - Money In"]
        elif "Contract - Money Out" in d:
            splits.append(d)
        else:
            for k in ("nome_income1", "nome_income2", "nome_income3"):
                if k in d:
                    nomes.append(d[k])

    incomes = []
    for i, split in enumerate(splits):
        nome_full = nomes[i] if i < len(nomes) else ""
        desc = nome_full
        if desc.startswith(PERIODO):
            desc = desc[len(PERIODO):]
        desc = desc.strip()
        incomes.append({
            "descricao": desc,
            "money_out": split["Contract - Money Out"],
            "org_pct": split["SPLIT AMOUNT | Organization (%)"],
            "rights_pct": split["SPLIT AMOUNT | Rights-Holder (%)"],
        })
    return money_in, incomes


def build():
    regras = []
    for key, value in REGRAS.items():
        catalogo = key[0]
        fonte = key[1]
        historico = key[2] if len(key) > 2 else None
        money_in, incomes = parse_rule(value)
        regras.append({
            "catalogo": catalogo,
            "fonte": fonte,
            "historico": historico,
            "money_in": money_in,
            "incomes": incomes,
        })
    return {"periodo": PERIODO, "regras": regras}


if __name__ == "__main__":
    out_path = Path(__file__).resolve().parent.parent / "data" / "direct_incomes" / "regras.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(data['regras'])} regras escritas em {out_path}")
    # Sanidade: nenhuma regra sem incomes
    vazias = [(r["catalogo"], r["fonte"], r["historico"]) for r in data["regras"] if not r["incomes"]]
    if vazias:
        print(f"AVISO: {len(vazias)} regra(s) sem incomes: {vazias}")
