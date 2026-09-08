"""Gera o favicon do lyra a partir da lira do kit da marca.

Não redesenha nada: pega `assets/lyra_icon.png` (a lira oficial) e só corrige
duas coisas mecânicas antes de reduzir.

1. **Deixa quadrado.** O PNG do kit é 1024x1133. Favicon é quadrado por
   definição, então o navegador espreme ou sobra tarja — a lira sai deformada.
2. **Corta a margem transparente.** O kit traz ~9% de vazio de cada lado. Num
   ícone de 16px isso são ~1,5px de nada em cada borda, num orçamento de 16.

Só isso já dá ~25% mais desenho dentro da mesma caixa.

Uma tentativa anterior redesenhou a lira com traço grosso para "sobreviver" a
16px. Foi erro: resolveu um caso raro (tela não-hidpi) trocando a marca por uma
aproximação — volutas viradas bolotas, 3 cordas em vez de 6. Em tela hidpi, que
é o normal hoje, o navegador pede o ícone de 32px, onde a lira do kit lê bem.
Se algum dia a leitura a 16px virar problema de verdade, a decisão é de quem
cuida da marca, não daqui.

Rodar:  python scripts/gerar_favicon.py
"""

from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
ASSETS = RAIZ / "assets"

ORIGEM = ASSETS / "lyra_icon.png"   # a lira do kit, sem alteração
FOLGA = 0.02                        # respiro mínimo para a lira não encostar na borda


def quadrado_justo(im: Image.Image, folga: float = FOLGA) -> Image.Image:
    """Corta no desenho e centra num quadrado."""
    corte = im.crop(im.split()[3].getbbox())
    lado = int(max(corte.size) * (1 + folga * 2))
    fora = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    fora.paste(corte, ((lado - corte.width) // 2, (lado - corte.height) // 2))
    return fora


def main() -> None:
    marca = quadrado_justo(Image.open(ORIGEM).convert("RGBA"))

    marca.resize((512, 512), Image.LANCZOS).save(ASSETS / "lyra_favicon.png")
    marca.save(
        ASSETS / "lyra_favicon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    print(f"gravado {ASSETS / 'lyra_favicon.png'} (512x512, a partir de {ORIGEM.name})")
    print(f"gravado {ASSETS / 'lyra_favicon.ico'} (16..256)")


if __name__ == "__main__":
    main()
