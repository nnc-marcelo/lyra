"""Gera a versão reversa do lockup — a que vai sobre fundo escuro.

O kit da marca não traz versão reversa, e ela é necessária: o wordmark "LYRA"
é #003fbc, que sobre a barra lateral do tema escuro (#1c2541) dá 1,75:1 e
simplesmente some.

Esta é uma troca de COR, decidida com o Marcelo em 08/09/2026, não um
redesenho: o wordmark passa para #9ecbf4 — o azul-claro que a paleta da Nas
Nuvens já tem, e que rende 8,85:1 sobre o mesmo fundo. A lira segue na
terracota #d3744f, que atravessa os dois temas sem mudar (5,2:1 no escuro).

O traço, as proporções e o desenho não são tocados.

Rodar:  python scripts/gerar_logo_escuro.py
"""

import re
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
ASSETS = RAIZ / "assets"

AZUL_CLARO = "#9ecbf4"      # da paleta Nas Nuvens
AZUL_MARCA = (0, 63, 188)   # #003fbc, como está no PNG do kit


def _e_o_wordmark(r: int, g: int, b: int) -> bool:
    """Distingue o azul do wordmark da terracota da lira. Pega também os pixels
    de borda (anti-aliasing), que mantêm a cor e só perdem alfa."""
    return b > r + 40 and b > g + 30


def main() -> None:
    alvo = tuple(int(AZUL_CLARO[i : i + 2], 16) for i in (1, 3, 5))

    # SVG: troca exata, é só o fill do path das letras
    svg = (ASSETS / "lyra_lockup_horizontal.svg").read_text(encoding="utf-8")
    novo, n = re.subn(r'fill="#003fbc"', f'fill="{AZUL_CLARO}"', svg)
    if n != 1:
        raise SystemExit(f"esperava 1 fill de wordmark no SVG, achei {n}")
    (ASSETS / "lyra_lockup_horizontal_dark.svg").write_text(novo, encoding="utf-8")

    # PNG: remapeia só os pixels do wordmark, preservando o alfa
    im = Image.open(ASSETS / "lyra_lockup_horizontal.png").convert("RGBA")
    px = im.load()
    trocados = 0
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a and _e_o_wordmark(r, g, b):
                px[x, y] = (*alvo, a)
                trocados += 1
    im.save(ASSETS / "lyra_lockup_horizontal_dark.png")

    print(f"gravado {ASSETS / 'lyra_lockup_horizontal_dark.svg'}")
    print(f"gravado {ASSETS / 'lyra_lockup_horizontal_dark.png'} ({trocados} px do wordmark)")


if __name__ == "__main__":
    main()
