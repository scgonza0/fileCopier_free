"""Genera el icono personalizado de FileCopier (archivo .ico multiresolucion).

Diseno: fondo azul oscuro circular con dos paginas apiladas (sombra + frontal
blanca con lineas de "texto") y una flecha verde de copia, representando la
copia selectiva de archivos.

Escribe el formato .ico manualmente (1 directorio + N frames como PNG) para
soportar todas las resoluciones que Windows usa: 16/32/48/64/128/256.

Run:  python tools/make_icon.py
"""
import struct
import zlib
from pathlib import Path
from PIL import Image, ImageDraw, PngImagePlugin

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "assets" / "filecopier.ico"
OUT.parent.mkdir(parents=True, exist_ok=True)


def make_frame(size: int) -> Image.Image:
    """Genera un frame RGBA del icono a la resolucion dada."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    margin = max(2, size // 16)
    # Fondo circular azul oscuro
    d.ellipse([margin, margin, size - margin, size - margin], fill=(25, 42, 78, 255))
    d.ellipse([margin + 1, margin + 1, size - margin - 1, size - margin - 1],
              outline=(52, 84, 136, 255), width=max(1, size // 32))

    # Pagina base (blanca) con sombra
    pw = int(size * 0.50)
    ph = int(size * 0.58)
    px = int(size * 0.22)
    py = int(size * 0.24)
    off = max(2, size // 20)
    # sombra trasera
    d.rectangle([px + off, py + off, px + pw + off, py + ph + off],
                fill=(120, 135, 160, 160))
    # pagina trasera (gris)
    d.rectangle([px + off // 2, py + off // 2, px + pw + off // 2, py + ph + off // 2],
                fill=(220, 226, 234, 255))
    # pagina frontal blanca
    d.rectangle([px, py, px + pw, py + ph], fill=(255, 255, 255, 255),
                outline=(40, 60, 95, 255), width=max(1, size // 48))
    # lineas de texto
    line_h = max(2, size // 34)
    yy = py + int(ph * 0.18)
    line_w = int(pw * 0.62)
    line_x = px + int(pw * 0.14)
    for i in range(4):
        lw = line_w if i != 2 else int(line_w * 0.55)
        d.rectangle([line_x, yy, line_x + lw, yy + line_h - 1], fill=(70, 95, 130, 230))
        yy += line_h + max(2, size // 40)

    # Flecha verde de copia (apunta a la derecha)
    arrow_c = (46, 175, 90, 255)
    aw = int(size * 0.13)
    ax = px + pw - int(size * 0.04)
    ay = py + int(ph * 0.55)
    d.rectangle([ax - aw, ay - int(aw * 0.35), ax + int(aw * 0.4), ay + int(aw * 0.35)],
                fill=arrow_c)
    tip = [(ax + int(aw * 0.4), ay - int(aw * 0.85)),
           (ax + int(aw * 1.1), ay),
           (ax + int(aw * 0.4), ay + int(aw * 0.85))]
    d.polygon(tip, fill=arrow_c)

    return img


def write_ico(output: Path, frames: list[Image.Image]):
    """Escribe un .ico multiresolucion: cabecera + directorio + frames PNG."""
    import io
    # Convertir cada frame a bytes PNG
    png_datas = []
    for f in frames:
        buf = io.BytesIO()
        f.save(buf, format="PNG")
        png_datas.append(buf.getvalue())

    n = len(frames)
    # Cabecera .ico: reserved(2) + type(2)=1 + count(2)
    header = struct.pack("<HHH", 0, 1, n)
    # Cada entrada de directorio: width(1), height(1), colors(1), reserved(1),
    # planes(2), bitcount(2), bytes(4), offset(4)  => 16 bytes
    entries = bytearray()
    offset = 6 + n * 16   # cabecera(6) + n*16 bytes de directorio
    for i, png in enumerate(png_datas):
        s = frames[i].size[0]
        w = s if s < 256 else 0   # 0 significa 256 en el formato .ico
        h = s if s < 256 else 0
        entries += struct.pack("<BBBBHHII",
                               w, h, 0, 0,   # width, height, colorcount, reserved
                               1, 32,        # planes(=1), bitcount(=32bpp RGBA)
                               len(png), offset)
        offset += len(png)

    with open(output, "wb") as fp:
        fp.write(header)
        fp.write(entries)
        for png in png_datas:
            fp.write(png)


SIZES = [16, 32, 48, 64, 128, 256]
frames = [make_frame(s) for s in SIZES]
write_ico(OUT, frames)

# --- Exportar PNG (Linux) -------------------------------------------
png_out = HERE / "assets" / "filecopier_256.png"
frames[-1].save(png_out, format="PNG")
print(f"PNG (Linux): {png_out}  ({png_out.stat().st_size/1024:.1f} KB)")

# --- Exportar ICNS (macOS) via PNGs + iconutil ----------------------
icns_dir = HERE / "assets" / "filecopier.iconset"
icns_dir.mkdir(exist_ok=True)
# macOS iconset necesita pares 1x y 2x para cada tamaño
iconset_sizes = [16, 32, 64, 128, 256, 512]
for s in iconset_sizes:
    f = make_frame(s)
    f.save(icns_dir / f"icon_{s}x{s}.png", format="PNG")
    # versión @2x (hasta 512 → 1024)
    if s <= 256:
        f2 = make_frame(s * 2)
        f2.save(icns_dir / f"icon_{s}x{s}@2x.png", format="PNG")
icns_out = HERE / "assets" / "filecopier.icns"
print(f"iconset macOS: {icns_dir}  ({len(list(icns_dir.glob('*.png')))} PNGs)")
print(f"(para generar .icns ejecutar: iconutil -c icns {icns_dir})")

# Verificar .ico
im = Image.open(OUT)
sizes = []
try:
    while True:
        sizes.append(im.size)
        im.seek(im.tell() + 1)
except EOFError:
    pass
print(f"icono generado: {OUT}")
print(f"  tamano: {OUT.stat().st_size/1024:.1f} KB")
print(f"  frames: {sizes}")
print(f"  OK multiresolucion: {len(frames) == len(sizes)}")
