"""
2_filtrar_contenido_sin_tablas.py
─────────────────────────────────
PASO 2 del flujo.

Toma el JSON crudo de opendataloader_pdf y se queda únicamente con los
elementos de tipo "heading", "paragraph" y "list".

ENTRADA:  JSONObtenidos/<nombre_pdf>.json
SALIDA:   JSONObtenidos/contenido_sin_tablas.json
"""

import json
import os
import glob
from _detectar_pdf import detectar_pdf, nombre_base

# Localizar el JSON crudo que corresponde al PDF seleccionado
pdf_path  = detectar_pdf()
base      = nombre_base(pdf_path)
json_crudo = os.path.join("JSONObtenidos", f"{base}.json")

if not os.path.isfile(json_crudo):
    raise FileNotFoundError(
        f"No se encontró {json_crudo}.\n"
        f"Ejecuta primero: python 1_extraer_pdf_opendataloader.py"
    )

print(f"Leyendo: {json_crudo}")

with open(json_crudo, "r", encoding="utf-8") as f:
    documento = json.load(f)

elementos_filtrados = [
    elem for elem in documento["kids"]
    if elem.get("type") in ("heading", "paragraph", "list")
]

nuevo_json = {
    "file_name": documento["file name"],
    "kids":      elementos_filtrados
}

with open("JSONObtenidos/contenido_sin_tablas1.json", "w", encoding="utf-8") as f:
    json.dump(nuevo_json, f, ensure_ascii=False, indent=4)

print(f"Filtrado: {len(elementos_filtrados)} elementos → JSONObtenidos/contenido_sin_tablas.json")
