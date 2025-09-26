import uuid
import random
from datetime import datetime

# ==============================
# Helpers
# ==============================
def generar_id_unico():
    """Genera un ID único para libros y préstamos"""
    return str(uuid.uuid4())[:8]

def sincronizar_estados_libros(user_data):
    """Sincroniza los estados de los libros basándose en los préstamos activos"""
    libros = user_data.get("libros_disponibles", [])
    prestamos = user_data.get("prestamos_activos", [])
    
    # Primero, asegurar que todos los libros tengan ID
    for libro in libros:
        if not libro.get("id"):
            libro["id"] = generar_id_unico()
    
    # Luego, actualizar estados
    ids_prestados = {p.get("libro_id") for p in prestamos if p.get("libro_id")}
    
    for libro in libros:
        if libro.get("id") in ids_prestados:
            libro["estado"] = "prestado"
        else:
            libro["estado"] = "disponible"
    
    return user_data

def buscar_libro_por_titulo(libros, titulo_busqueda):
    """Busca libros por título y devuelve una lista de coincidencias"""
    titulo_busqueda = (titulo_busqueda or "").lower().strip()
    resultados = []
    for libro in libros:
        if isinstance(libro, dict):
            titulo_libro = (libro.get("titulo") or "").lower()
            if titulo_busqueda in titulo_libro or titulo_libro in titulo_busqueda:
                resultados.append(libro)
    return resultados

def buscar_libro_por_titulo_exacto(libros, titulo_busqueda):
    """Busca un libro por título y devuelve el primero que coincida"""
    titulo_busqueda = (titulo_busqueda or "").lower().strip()
    for libro in libros:
        if isinstance(libro, dict):
            titulo_libro = (libro.get("titulo") or "").lower()
            if titulo_busqueda in titulo_libro or titulo_libro in titulo_busqueda:
                return libro
    return None

def buscar_libros_por_autor(libros, autor_busqueda):
    autor_busqueda = (autor_busqueda or "").lower().strip()
    resultados = []
    for libro in libros:
        if isinstance(libro, dict):
            autor_libro = (libro.get("autor") or "").lower()
            if autor_busqueda in autor_libro or autor_libro in autor_busqueda:
                resultados.append(libro)
    return resultados

def generar_id_prestamo():
    return f"PREST-{datetime.now().strftime('%Y%m%d')}-{generar_id_unico()}"

def get_random_phrase(phrase_list):
    """Selecciona una frase aleatoria de una lista"""
    return random.choice(phrase_list)