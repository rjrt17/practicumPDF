"""
1_extraer_pdf_opendataloader.py
─────────────────────────────────
PASO 1 del flujo.

Usa la librería `opendataloader_pdf` (requiere Java instalado) para leer
el PDF y generar un JSON con TODO el contenido detectado por la
herramienta: headings, paragraphs, lists, tables, images, etc.

ENTRADA:  <pdf detectado o seleccionado>
SALIDA:   JSONObtenidos/<nombre_pdf>.json
          JSONObtenidos/<nombre_pdf>.md
"""

import os
import opendataloader_pdf
from _detectar_pdf import detectar_pdf, nombre_base

pdf_path = detectar_pdf()
base     = nombre_base(pdf_path)

os.makedirs("JSONObtenidos", exist_ok=True)

print(f"Procesando: {pdf_path}")

opendataloader_pdf.convert(
    input_path=[pdf_path],
    output_dir="JSONObtenidos",
    format="markdown,json"
)

print(f"Extracción completada → JSONObtenidos/{base}.json")
