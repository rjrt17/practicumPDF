"""
4_extraer_entidades.py
────────────────────────
PASO 4 del flujo.

Lee documento_final_ordenado.json (salida del paso 3, jerárquico) y
extrae información semántica estructurada sin depender de nombres de
archivo, posiciones fijas ni estructura rígida.

ESTRATEGIA GENÉRICA (3 capas)
──────────────────────────────
  Capa 1 — PARES ETIQUETA/VALOR en tablas
    Cada table_row con 2 celdas: si col_1 coincide con un sinónimo
    del diccionario, extrae col_2 como valor.

  Capa 2 — CONTEXTO POR SECCIÓN (headings)
    Cuando un heading activa una sección por sinónimos, todo lo que
    le sigue hasta el próximo heading se agrupa en esa sección.

  Capa 3 — REGEX sobre texto completo
    Para fechas, emails y URLs que no aparecen como par etiqueta/valor.

ENTRADA:  JSONObtenidos/documento_final_ordenado.json
SALIDA:   JSONObtenidos/documento_semantico.json
"""

from __future__ import annotations

import json
import re
import logging
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
#  CONFIGURACIÓN — diccionarios de sinónimos
#  Amplía estas listas para soportar otros PDF sin cambiar
#  ninguna otra parte del código.
# ══════════════════════════════════════════════════════════

SINONIMOS_ETIQUETA: dict[str, list[str]] = {
    "asignatura":        ["nombre de la asignatura", "asignatura",
                          "materia", "nombre de la materia",
                          "programa de asignatura"],
    "codigo":            ["código", "codigo", "cod", "code",
                          "código de la asignatura", "id asignatura"],
    "carrera":           ["carrera", "programa", "carrera académica",
                          "nombre de la carrera"],
    "facultad":          ["facultad", "escuela"],
    "area":              ["área académica", "area académica", "area academica"],
    "modalidad":         ["modalidad de estudio", "modalidad"],
    "seccion":           ["sección departamental", "seccion departamental"],
    "campo_formacion":   ["campo de formación del currículo",
                          "campo de formación", "campo de formación:",
                          "campo de formacion"],
    "creditos":          ["número de créditos", "créditos", "creditos",
                          "número de créditos/horas", "número de crédito horas",
                          "credito"],
    "horas":             ["horas", "total horas", "número de horas"],
    "periodo":           ["período académico", "periodo académico",
                          "período académico ordinario (pao) en el que se imparte",
                          "período académico:", "ciclo", "semestre", "pao"],
    "pre_requisitos":    ["pre-requisitos y co-requisitos", "pre-requisitos",
                          "pre requisitos", "prerequisitos", "pre-requisitos:"],
    "correquisitos":     ["correquisitos", "co-requisitos", "correquisitos:"],
    "unidad_curricular": ["unidad de organización curricular",
                          "unidad curricular", "campo de formación"],
    "importancia":       ["importancia de la asignatura en el perfil de egreso de la carrera",
                          "importancia de la asignatura", "importancia",
                          "descripción general de la asignatura",
                          "descripcion general de la asignatura",
                          "b. descripción general de la asignatura"],
    "docente":           ["nombre del docente", "docente coordinador",
                          "nombre docente"],
    "titulo_tercer":     ["título(s) de tercer nivel", "título tercer nivel",
                          "titulo(s) de tercer nivel"],
    "titulo_cuarto":     ["título(s) de cuarto nivel", "título cuarto nivel",
                          "titulo(s) de cuarto nivel"],
    "departamento":      ["departamento:", "departamento"],
    "email":             ["correo electrónico", "correo", "email", "e-mail"],
    "curriculum":        ["currículum resumido", "curriculum resumido",
                          "curriculum"],
}

SINONIMOS_SECCION: dict[str, list[str]] = {
    "competencias_genericas":    ["competencias genéricas",
                                  "competencias genericas de la utpl"],
    "competencias_especificas":  ["competencias específicas",
                                  "competencias específicas de la carrera",
                                  "competencia/s específica/s a la que aporta la asignatura"],
    "resultados_aprendizaje":    ["resultados de aprendizaje",
                                  "resultado de aprendizaje",
                                  "resultados de aprendizaje de la asignatura",
                                  "logros de aprendizaje",
                                  "c. resultados de aprendizaje de la asignatura",
                                  "resultados de aprendizaje del perfil de egreso al que aporta la asignatura"],
    "contenidos":                ["contenidos a desarrollarse", "contenidos",
                                  "d. contenidos", "temas", "temario"],
    "actividades":               ["actividades del componente",
                                  "estrategias de enseñanza"],
    "metodologia":               ["metodología", "metodologia",
                                  "e. metodología"],
    "evaluacion":                ["evaluación de la asignatura",
                                  "evaluacion de la asignatura",
                                  "f. procedimientos de evaluación",
                                  "procedimientos de evaluación",
                                  "sistema de evaluación",
                                  "criterios de evaluación"],
    "bibliografia":              ["bibliografía", "bibliografia",
                                  "g. bibliografía",
                                  "recursos a utilizar en el desarrollo de la asignatura",
                                  "f. recursos a utilizar en el desarrollo de la asignatura",
                                  "bibliografía básica",
                                  "recursos educativos abiertos (rea)",
                                  "recursos educativos abiertos"],
    "fechas":                    ["fechas importantes", "cronograma",
                                  "calendario académico"],
    "aprobacion":                ["h. elaboración y aprobación",
                                  "elaboración y aprobación",
                                  "elaboracion y aprobacion"],
}

# Patrón de inicio de semana: "Semana N" como única celda de primera fila
PATRON_SEMANA = re.compile(r"^semana\s+(\d+)$", re.IGNORECASE)

REGEX_FECHA = re.compile(
    r"semana\s+\d+\s*[-–]\s*del\s+\d{2}/\d{2}/\d{4}\s+al\s+\d{2}/\d{2}/\d{4}"
    r"|del\s+\d{2}/\d{2}/\d{4}\s+al\s+\d{2}/\d{2}/\d{4}"
    r"|\d{2}/\d{2}/\d{4}",
    re.IGNORECASE
)
REGEX_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
REGEX_URL   = re.compile(r"https?://[^\s]+")

# Cabeceras que identifican tabla de HORARIO → no confundir con ficha docente
CABECERAS_HORARIO = {"paralelo", "día", "dia", "aula", "horario"}


# ══════════════════════════════════════════════════════════
#  DATA CLASSES
# ══════════════════════════════════════════════════════════

@dataclass
class Docente:
    nombre:         str = ""
    titulo_tercero: str = ""
    titulo_cuarto:  str = ""
    departamento:   str = ""
    email:          str = ""
    curriculum:     str = ""

@dataclass
class Semana:
    numero:       int       = 0
    competencias: list[str] = field(default_factory=list)
    contenidos:   list[str] = field(default_factory=list)
    resultados:   list[str] = field(default_factory=list)
    actividades:  list[str] = field(default_factory=list)

@dataclass
class DocumentoSemantico:
    archivo:                  str            = ""
    fecha_procesamiento:      str            = ""
    metadatos:                dict[str, Any] = field(default_factory=dict)
    docentes:                 list[Docente]  = field(default_factory=list)
    competencias_genericas:   list[str]      = field(default_factory=list)
    competencias_especificas: list[str]      = field(default_factory=list)
    resultados_aprendizaje:   list[str]      = field(default_factory=list)
    semanas:                  list[Semana]   = field(default_factory=list)
    evaluacion:               list[dict]     = field(default_factory=list)
    bibliografia:             list[str]      = field(default_factory=list)
    fechas:                   list[str]      = field(default_factory=list)
    emails:                   list[str]      = field(default_factory=list)
    urls:                     list[str]      = field(default_factory=list)
    texto_completo:           str            = ""


# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════

def normalizar(texto: str) -> str:
    texto = texto.lower().replace("\n", " ").replace(":", "")
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.split()).strip()


def coincidir(texto: str, sinonimos: dict[str, list[str]]) -> str | None:
    tn = normalizar(texto)
    for canon, variantes in sinonimos.items():
        for v in variantes:
            vn = normalizar(v)
            if tn == vn or tn.startswith(vn):
                return canon
    return None


def limpiar(texto: str) -> str:
    return " ".join(texto.replace("\n", " ").split()).strip(": ").strip()


def dedup(lst: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in lst if x and x not in seen and not seen.add(x)]  # type: ignore


def es_biblio(texto: str) -> bool:
    tn = normalizar(texto)
    return bool(
        re.match(r"^\[?\d+\]", texto)
        or tn.startswith("recurso")
        or tn.startswith("bibliografi")
        or tn.startswith("basica")
        or tn.startswith("complementaria")
    )


# ══════════════════════════════════════════════════════════
#  HELPERS DE TABLA (trabajan directo sobre rows/cells del
#  documento_final_ordenado.json — sin árbol reconstruido)
# ══════════════════════════════════════════════════════════

def celdas_de_fila(fila: dict) -> list[str]:
    """Devuelve los contenidos no vacíos de las celdas de una fila."""
    return [
        c.get("content", "").strip()
        for c in fila.get("cells", [])
        if c.get("content", "").strip()
    ]


def pares_de_tabla(tabla: dict) -> dict[str, str]:
    """Extrae pares etiqueta→valor de todas las filas con 2 columnas."""
    pares: dict[str, str] = {}
    for fila in tabla.get("rows", []):
        celdas = celdas_de_fila(fila)
        if len(celdas) >= 2:
            canon = coincidir(celdas[0], SINONIMOS_ETIQUETA)
            if canon:
                pares[canon] = limpiar(celdas[1])
    return pares


def es_tabla_horario(tabla: dict) -> bool:
    """Primera fila con ≥3 celdas que contienen cabeceras de horario."""
    filas = tabla.get("rows", [])
    if not filas:
        return False
    cols = celdas_de_fila(filas[0])
    if len(cols) >= 3:
        if {normalizar(c) for c in cols} & CABECERAS_HORARIO:
            return True
    return False


def extraer_docente(tabla: dict) -> Docente | None:
    if es_tabla_horario(tabla):
        return None
    pares = pares_de_tabla(tabla)
    if "docente" not in pares:
        return None
    return Docente(
        nombre         = pares.get("docente", ""),
        titulo_tercero = pares.get("titulo_tercer", ""),
        titulo_cuarto  = pares.get("titulo_cuarto", ""),
        departamento   = pares.get("departamento", ""),
        email          = pares.get("email", ""),
        curriculum     = pares.get("curriculum", ""),
    )


def extraer_semana(tabla: dict) -> Semana | None:
    """Si la primera fila tiene una sola celda tipo 'Semana N', extrae la semana."""
    filas = tabla.get("rows", [])
    if not filas:
        return None
    primera = celdas_de_fila(filas[0])
    if not primera:
        return None
    m = PATRON_SEMANA.match(primera[0].strip())
    if not m:
        return None

    semana = Semana(numero=int(m.group(1)))

    for fila in filas[1:]:
        celdas = celdas_de_fila(fila)
        if len(celdas) < 2:
            continue
        en = normalizar(celdas[0])
        val = limpiar(celdas[1])

        if coincidir(en, {"x": SINONIMOS_SECCION["competencias_especificas"]
                          + SINONIMOS_SECCION["competencias_genericas"]}):
            semana.competencias.append(val)
        elif coincidir(en, {"x": SINONIMOS_SECCION["contenidos"]}):
            semana.contenidos.append(val)
        elif coincidir(en, {"x": SINONIMOS_SECCION["resultados_aprendizaje"]}):
            semana.resultados.append(val)
        elif coincidir(en, {"x": SINONIMOS_SECCION["actividades"]}):
            semana.actividades.append(val)

    return semana


# ══════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL
#  Trabaja directamente sobre la lista "elements" del
#  documento_final_ordenado.json (no necesita árbol externo)
# ══════════════════════════════════════════════════════════

def extraer_entidades(elements: list[dict], archivo: str = "") -> DocumentoSemantico:

    doc = DocumentoSemantico(
        archivo=archivo,
        fecha_procesamiento=datetime.now(timezone.utc).isoformat()
    )

    metadatos_tmp: dict[str, str] = {}
    seccion_activa: str | None    = None
    buffer_seccion: list[str]     = []
    partes_texto:   list[str]     = []

    def volcar():
        nonlocal buffer_seccion, seccion_activa
        items = dedup([b for b in buffer_seccion if b.strip()])
        if   seccion_activa == "competencias_genericas":
            doc.competencias_genericas.extend(items)
        elif seccion_activa == "competencias_especificas":
            doc.competencias_especificas.extend(items)
        elif seccion_activa == "resultados_aprendizaje":
            doc.resultados_aprendizaje.extend(items)
        elif seccion_activa == "bibliografia":
            doc.bibliografia.extend(items)
        elif seccion_activa == "evaluacion":
            doc.evaluacion.extend([{"descripcion": i} for i in items])
        buffer_seccion = []

    for elem in elements:
        tipo    = elem.get("type", "")
        content = elem.get("content", "").strip()

        # ── HEADING ──────────────────────────────────────────
        if tipo == "heading":
            volcar()
            seccion_activa = coincidir(content, SINONIMOS_SECCION)
            partes_texto.append(content)

        # ── PARAGRAPH ────────────────────────────────────────
        elif tipo == "paragraph":
            partes_texto.append(content)
            if seccion_activa == "fechas":
                buffer_seccion.append(content)
            doc.fechas.extend(REGEX_FECHA.findall(content))

        # ── LIST ─────────────────────────────────────────────
        elif tipo == "list":
            items_lista = [
                item.get("content", "").strip()
                for item in elem.get("items", [])
                if item.get("content", "").strip()
            ]
            partes_texto.extend(items_lista)
            biblio = [i for i in items_lista if es_biblio(i)]
            resto  = [i for i in items_lista if not es_biblio(i)]
            doc.bibliografia.extend(biblio)
            buffer_seccion.extend(resto)

        # ── TABLE ────────────────────────────────────────────
        elif tipo == "table":

            # Texto de todas las celdas al corpus
            for fila in elem.get("rows", []):
                for celda in celdas_de_fila(fila):
                    partes_texto.append(celda)

            # Intento 1: tabla de semana semanal
            semana = extraer_semana(elem)
            if semana:
                existente = next(
                    (s for s in doc.semanas if s.numero == semana.numero), None
                )
                if existente:
                    existente.competencias.extend(semana.competencias)
                    existente.contenidos.extend(semana.contenidos)
                    existente.resultados.extend(semana.resultados)
                    existente.actividades.extend(semana.actividades)
                else:
                    doc.semanas.append(semana)
                continue

            # Intento 2: ficha de docente
            docente = extraer_docente(elem)
            if docente:
                doc.docentes.append(docente)
                continue

            # Intento 3: pares etiqueta/valor → metadatos generales
            pares = pares_de_tabla(elem)
            if pares:
                campos_docente = {"docente", "titulo_tercer", "titulo_cuarto",
                                  "departamento", "email", "curriculum"}
                pares_meta = {k: v for k, v in pares.items()
                              if k not in campos_docente}
                if pares_meta:
                    metadatos_tmp.update(pares_meta)
                    continue

            # Intento 4: tabla con cabecera de sección en primera fila
            #            (ej: "Competencias genéricas de la UTPL" → resto son valores)
            filas_tabla = elem.get("rows", [])
            if filas_tabla:
                primera_celdas = celdas_de_fila(filas_tabla[0])
                if len(primera_celdas) == 1:
                    nueva = coincidir(primera_celdas[0], SINONIMOS_SECCION)
                    if nueva:
                        volcar()
                        seccion_activa = nueva
                        for fila in filas_tabla[1:]:
                            buffer_seccion.extend(celdas_de_fila(fila))
                        continue

            # Intento 5: contenido para la sección activa ya establecida
            if seccion_activa:
                for fila in elem.get("rows", []):
                    celdas = celdas_de_fila(fila)
                    if len(celdas) == 1:
                        nueva = coincidir(celdas[0], SINONIMOS_SECCION)
                        if nueva:
                            volcar()
                            seccion_activa = nueva
                        else:
                            buffer_seccion.append(celdas[0])
                    else:
                        buffer_seccion.extend(celdas)

    volcar()

    # ── Metadatos consolidados ────────────────────────────────
    doc.metadatos = {
        "asignatura":        metadatos_tmp.get("asignatura", ""),
        "codigo":            metadatos_tmp.get("codigo", ""),
        "carrera":           metadatos_tmp.get("carrera", ""),
        "facultad":          metadatos_tmp.get("facultad", ""),
        "area":              metadatos_tmp.get("area", ""),
        "modalidad":         metadatos_tmp.get("modalidad", ""),
        "seccion":           metadatos_tmp.get("seccion", ""),
        "campo_formacion":   metadatos_tmp.get("campo_formacion", ""),
        "creditos":          metadatos_tmp.get("creditos", ""),
        "horas":             metadatos_tmp.get("horas", ""),
        "periodo":           metadatos_tmp.get("periodo", ""),
        "pre_requisitos":    metadatos_tmp.get("pre_requisitos", ""),
        "correquisitos":     metadatos_tmp.get("correquisitos", ""),
        "unidad_curricular": metadatos_tmp.get("unidad_curricular", ""),
        "importancia":       metadatos_tmp.get("importancia", ""),
        "docente_principal": doc.docentes[0].nombre if doc.docentes else "",
    }

    # ── Dedup y ordenamiento ──────────────────────────────────
    for s in doc.semanas:
        s.competencias = dedup(s.competencias)
        s.contenidos   = dedup(s.contenidos)
        s.resultados   = dedup(s.resultados)
        s.actividades  = dedup(s.actividades)
    doc.semanas.sort(key=lambda s: s.numero)

    doc.competencias_genericas   = dedup(doc.competencias_genericas)
    doc.competencias_especificas = dedup(doc.competencias_especificas)
    doc.resultados_aprendizaje   = dedup(doc.resultados_aprendizaje)
    doc.bibliografia             = dedup(doc.bibliografia)
    doc.fechas                   = dedup(doc.fechas)

    # ── Capa 3: regex sobre texto completo ────────────────────
    doc.texto_completo = "\n".join(partes_texto)
    doc.emails = dedup(REGEX_EMAIL.findall(doc.texto_completo))
    doc.urls   = dedup(REGEX_URL.findall(doc.texto_completo))
    doc.fechas = dedup(doc.fechas + REGEX_FECHA.findall(doc.texto_completo))

    return doc


# ══════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":

    entrada = Path("JSONObtenidos/documento_final_ordenado1.json")
    salida  = Path("JSONObtenidos/documento_semantico1.json")

    log.info(f"Leyendo: {entrada}")
    with open(entrada, "r", encoding="utf-8") as f:
        documento = json.load(f)

    log.info("Extrayendo entidades...")
    resultado = extraer_entidades(
        elements=documento["elements"],
        archivo=documento.get("file_name", "")
    )

    log.info(f"Guardando: {salida}")
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(asdict(resultado), f, ensure_ascii=False, indent=4)

    print()
    print("=" * 55)
    print("  documento_semantico.json generado")
    print("=" * 55)
    print(f"  Archivo           : {resultado.archivo}")
    print(f"  Asignatura        : {resultado.metadatos.get('asignatura')}")
    print(f"  Código            : {resultado.metadatos.get('codigo')}")
    print(f"  Carrera           : {resultado.metadatos.get('carrera')}")
    print(f"  Facultad          : {resultado.metadatos.get('facultad')}")
    print(f"  Área              : {resultado.metadatos.get('area')}")
    print(f"  Periodo           : {resultado.metadatos.get('periodo')}")
    print(f"  Docentes          : {len(resultado.docentes)}")
    for d in resultado.docentes:
        print(f"    - {d.nombre}")
    print(f"  Comp. genéricas   : {len(resultado.competencias_genericas)}")
    print(f"  Comp. específicas : {len(resultado.competencias_especificas)}")
    print(f"  Result. aprendiz  : {len(resultado.resultados_aprendizaje)}")
    print(f"  Semanas           : {len(resultado.semanas)}")
    print(f"  Bibliografía      : {len(resultado.bibliografia)}")
    print(f"  Fechas            : {len(resultado.fechas)}")
    print(f"  Emails            : {len(resultado.emails)}")
    print(f"  URLs              : {len(resultado.urls)}")
    print(f"  Palabras totales  : {len(resultado.texto_completo.split())}")
    print("=" * 55)
