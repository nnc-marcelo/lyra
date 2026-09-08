"""Gera o favicon do lyra — o corte óptico da lira para tamanho pequeno.

Por que este script existe (não copie o PNG do kit da marca por cima):

A lira do kit (`assets/lyra_icon.png`, `lyra_lockup_horizontal.*`) é desenhada
em traço fino — o traço tem ~1,5% da largura. Isso é lindo a 48px ou mais e
some a 16px: as cordas viram nada e a peça inteira vira uma mancha rosa clara.
Engrossar o traço do desenho original também não resolve; a 16px sobram ~14
pixels úteis e não cabe.

A saída daqui é um desenho PRÓPRIO para tamanho pequeno, com a mesma silhueta:
traço ~11% da largura, 3 cordas em vez de 6, tela quadrada e sem margem
transparente (a margem do kit custava 3px dos 16). É a prática normal de
"optical size" de qualquer identidade — a mesma marca, cortada para o tamanho
em que vai ser vista.

Onde cada arquivo é usado:
  assets/lyra_favicon.png  — st.set_page_config(page_icon=...) e o
                             st.logo(icon_image=...) da barra lateral recolhida.
                             Renderiza entre 16 e 32px. É este que precisa do
                             corte pesado.
  assets/lyra_favicon.ico  — não usado pelo app hoje; gerado por completude.
  assets/lyra_icon.*       — a lira fina do kit. Use de 48px para cima.

Rodar:  python scripts/gerar_favicon.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
ASSETS = RAIZ / "assets"

TERRACOTA = (211, 116, 79, 255)   # --nn-terracota / theme.orangeColor
N = 1024                          # resolução de desenho; a saída é reduzida daqui

# Proporções relativas a N. O traço grosso é o ponto: a 16px ele vira ~1,8px.
TRACO = 118
CORDA = 46
CORDAS = 3


def desenhar() -> Image.Image:
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy, r = 512, 585, 345

    # Corpo: anel grosso aberto no topo (um Ω). Ângulos do PIL: 0° às 3h,
    # crescendo no sentido horário porque o y cresce para baixo.
    d.arc([cx - r, cy - r, cx + r, cy + r], 302, 238, fill=TERRACOTA, width=TRACO)

    # Braços: sobem das pontas do corpo para fora e terminam em voluta.
    # A voluta vira um disco cheio — a espiral do kit não sobrevive a 16px.
    for ang, lado in ((302, 1), (238, -1)):
        ex = cx + r * math.cos(math.radians(ang))
        ey = cy + r * math.sin(math.radians(ang))
        px, py = cx + lado * 248, 178
        d.line([(ex, ey), (px, py)], fill=TERRACOTA, width=TRACO)
        d.ellipse([px - 92, py - 92, px + 92, py + 92], fill=TERRACOTA)

    # Travessão e cordas.
    d.line([(cx - 215, 300), (cx + 215, 300)], fill=TERRACOTA, width=int(TRACO * 0.85))
    for i in range(CORDAS):
        x = cx + (i - (CORDAS - 1) / 2) * 132
        d.line([(x, 318), (x, 792)], fill=TERRACOTA, width=CORDA)

    return im


def quadrado_justo(im: Image.Image, folga: float = 0.03) -> Image.Image:
    """Recorta no desenho e centra num quadrado. Sem isso o ícone perde pixel
    para margem transparente — caro a 16px — e sai esticado quando a tela não
    é quadrada (o PNG do kit é 512x567)."""
    corte = im.crop(im.split()[3].getbbox())
    lado = int(max(corte.size) * (1 + folga * 2))
    fora = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    fora.paste(corte, ((lado - corte.width) // 2, (lado - corte.height) // 2))
    return fora


def main() -> None:
    marca = quadrado_justo(desenhar())

    png = marca.resize((512, 512), Image.LANCZOS)
    png.save(ASSETS / "lyra_favicon.png")

    marca.save(
        ASSETS / "lyra_favicon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    print(f"gravado {ASSETS / 'lyra_favicon.png'} (512x512)")
    print(f"gravado {ASSETS / 'lyra_favicon.ico'} (16..256)")


if __name__ == "__main__":
    main()
