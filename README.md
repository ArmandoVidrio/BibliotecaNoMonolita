# Actividad Grupal 1: Principios de Diseño de Software.

[Instrucciones](https://www.notion.so/Instrucciones-277341ecaf0680f19a69d1758d952c0a?pvs=21)

# Formato Diseño de SW

**Versión: 0.2**

**Autor(es): Clemente Labrador, Emilio Maciel, Armando Vidrio Amador**

**Fecha: 28 de Septiembre de 2025**

**Historial de revisiones:**

---

## 1. Introducción (Caso de uso)

- **Descripción general del sistema / proyecto**

El objetivo del proyecto es desarrollar una Skill de Alexa “Mi biblioteca personal”, una herramienta que permitirá a los usuarios gestionar su colección de libros de manera eficiente. La interacción será controlada totalmente por voz: los usuarios podrán agregar, listar, prestar, devolver y eliminar libros, además de consultar el historial de movimientos.

- **Objetivo del documento**

El propósito de este documento es detallar el diseño y arquitectura de la Skill que vamos a desarrollar, especificar los requerimientos funcionales y no funcionales, presentar los diagramas de la arquitectura y el flujo de voz explicando las decisiones que se van tomando. Esta es nuestra guía como equipo de desarrollo.

- **Alcance** (qué incluye / qué no incluye)
    
    **Incluye:**
    
    - Funcionalidad para **agregar, listar, prestar, devolver y eliminar libros**.
    - **Historial** de préstamos y devoluciones.
    - Implementación de la persistencia de datos en **Amazon S3**
    - Diseño de interacciones por voz para cada acción soportada.
    
    **No incluye:**
    
    - Interfaz de usuario visual.
    - Funcionalidad para comprar o descargar libros.
    - Conexión o sincronización con plataformas externas.
    - Gestión de diferentes perfiles de usuario.
- **Actores principales**
    - **Usuario:** Persona que interactúa con la skill de Alexa para gestionar la biblioteca.
    - **Alexa:** Plataforma de asistente de voz que procesa las peticiones del usuario y responde.
    - **Sistema de persistencia:** Servicios en la nube para almacenamiento y consulta de datos (Amazon S3 y DynamoDB opcional).
- **Casos de uso / historias de usuario relevantes**
    - Como usuario, quiero **agregar libros** a mi biblioteca.
    - Como usuario, quiero **listar libros paginados**.
    - Como usuario, quiero **registrar préstamos y devoluciones**.
    - Como usuario, quiero **consultar el historial de movimientos**.
    - Como usuario, quiero **eliminar libros** de mi biblioteca (*flujo adicional*).

---

## 2. Problem Statement (Declaración del problema)

- **Contexto**
    
    Los lectores suelen tener colecciones de libros en constante crecimiento y, a menudo, los prestan o devuelven sin un control formal. Esto provoca dificultad para recordar qué títulos tienen disponibles, cuáles están prestados y a quién, así como pérdidas de tiempo para localizar libros específicos.
    
- **Problemas específicos que se quieren resolver**
    - Falta de un registro actualizado de préstamos y devoluciones.
    - Dificultad para listar y organizar títulos rápidamente por voz.
    - Ausencia de un historial que muestre los movimientos de la biblioteca.
- **Impacto / consecuencias de no resolverlos**
    - Desorganización y pérdida de control sobre la biblioteca personal.
    - Riesgo de extraviar libros prestados.
    - Frustración del usuario por falta de un acceso rápido y práctico a la información.
- **Restricciones del entorno**
    - La interacción debe ser exclusivamente por voz.
    - El sistema depende de servicios en la nube (Amazon S3).
    - Alexa debe responder con baja latencia (< 2 segundos en la mayoría de las solicitudes).
    - Un único usuario por biblioteca (no hay perfiles múltiples).

---

## 3. Requerimientos funcionales

| ID | Descripción | Actor | Prioridad | Criterios de aceptación |
| --- | --- | --- | --- | --- |
| RF-01 | **Agregar Libro** | Usuario, Skill de Alexa | Alta | “Alexa, agrega {título} a mi biblioteca” → Alexa confirma que el libro fue agregado. |
| RF-02 | **Listar Libros (paginados)** | Usuario, Skill de Alexa | Alta | “Alexa, lista mis libros” → Alexa lee hasta **10 libros por página** y ofrece continuar. |
| RF-03 | **Prestar Libro** | Usuario, Skill de Alexa | Alta | “Alexa, presta {título} a {persona}” → Alexa actualiza estado y confirma el préstamo. |
| RF-04 | **Devolver Libro** | Usuario, Skill de Alexa | Alta | “Alexa, registra la devolución de {título}” → Alexa actualiza estado y confirma la devolución. |
| RF-05 | **Consultar Historial de Movimientos** | Usuario, Skill de Alexa | Media | “Alexa, muéstrame el historial de préstamos y devoluciones” → Alexa enumera los últimos movimientos registrados. |
| RF-06 | **Eliminar Libro** (*flujo adicional*) | Usuario, Skill de Alexa | Media | “Alexa, elimina {título} de mi biblioteca” → Alexa confirma la eliminación o avisa si no existe. |

---

## 4. Requerimientos no funcionales

| ID | Atributo | Descripción | Métricas / criterios cuantitativos |
| --- | --- | --- | --- |
| RNF-01 | Rendimiento | La skill debe responder de forma fluida a los comandos de voz. | Tiempo de respuesta promedio < **2 segundos** en el 95% de las solicitudes. |
| RNF-02 | Persistencia de datos | El sistema debe recordar los libros y estados asociados al usuario entre sesiones. | La información debe conservarse al menos **90 días** sin pérdida. |
| RNF-03 | Compatibilidad | La skill debe estar disponible en cualquier dispositivo con Alexa integrado. | Ejecución correcta en **100%** de los dispositivos Alexa certificados. |
| RNF-04 | Usabilidad (VUI) | La interacción debe ser por voz, clara y natural. | Acciones principales completadas en máximo **3 turnos de diálogo**. |
| RNF-05 | Escalabilidad | Debe ser posible agregar nuevas funciones sin afectar las existentes. | Soportar la adición de al menos **3 nuevas funciones** sin rediseño completo. |
| RNF-06 | Comprensión del lenguaje natural | Debe reconocer modismos y expresiones coloquiales sin perder precisión. | Reconocimiento exitoso en al menos **90%** de frases con expresiones coloquiales. |

---

## 5. Arquitectura / Diseño – C4 Diagrams

Capa  1:

![image.png](attachment:5b07c0e4-5c23-4168-a4c5-9591dbc55877:image.png)

- Capa 2:
    
    ![image.png](attachment:343bbf58-65b1-44fe-b7e0-04f8cfc99337:image.png)
    
- Capa 3:
    
    ![image.png](attachment:e4c26d1c-d37d-46d9-b958-03a95b394bb2:image.png)
    
- 
- Descripción general de la arquitectura / componentes principales
    
    La skill se construirá como un sistema basado en **AWS Lambda** que recibe las peticiones desde **Alexa Voice Service (AVS)**.
    
    - **Usuario**: interactúa mediante comandos de voz en dispositivos con Alexa.
    - **Alexa Voice Service**: interpreta la intención del usuario y envía la solicitud a la función Lambda.
    - **AWS Lambda (Skill “Mi biblioteca personal”)**:
        - Punto de entrada donde se gestionan los intents.
        - Actualmente es un **monolito** (un solo archivo), pero se reorganizará en una estructura modular.
    - **Capas internas (desacopladas)**:
        1. **Intent Handlers**: manejan cada intención (Agregar, Listar, Prestar, Devolver, Consultar historial, Eliminar).
        2. **Servicios de dominio (Domain Services)**: lógica de negocio para la gestión de libros, préstamos y devoluciones.
        3. **Persistencia**: interacción con **Amazon S3** para almacenar y recuperar información de la biblioteca.
        4. **Utilidades**: funciones comunes (ej. validaciones, formateo de respuestas).
    - **Almacenamiento (Amazon S3)**: guarda la información de la biblioteca y permite consultar préstamos, devoluciones y listado de libros.
    
    **Reorganización desde el monolito**
    
    El archivo `lambda_function.py` se dividirá en:
    
    - `/handlers` → archivos con cada IntentHandler.
    - `/services` → lógica de negocio (ej. `BookService`, `LoanService`).
    - `/repositories` → clases para persistencia (ej. `S3Repository`).
    - `/utils` → funciones auxiliares (`utils.py` ya dado).

# Continuar a partir de aquí si no hay modificaciones

- **Nota:** incluir aquí los enlaces donde estén los diagramas C4 (GitHub, Notion, Figma, SharePoint, etc.)
    - Diagrama de Contexto (Level 1)
    - Diagrama de Contenedores (Level 2)
    - Diagrama de Componentes (Level 3)
    - (Opcional) Diagrama de clases / código (Nivel 4)

---

## 6. Diseño VUI / Diagramas de flujo de voz

- Objetivo del diseño VUI
- Estilo, tono y lenguaje de voz
- Escenarios de uso por voz (cuando, dónde, dispositivos, entorno)
- Diagrama(s) de flujo de conversación / voz
    - Inicio de la interacción
    - Alternativas / ramas de diálogo
    - Manejo de errores / fallback / confirmaciones
- Consideraciones especiales (latencia, reconocimiento de voz, fallos, etc.)

---

## 7. Secciones adicionales recomendadas

- Definiciones, Acrónimos, Glosario
- Dependencias externas / integraciones (APIs, servicios, librerías)
- Supuestos y restricciones (Assumptions & Constraints)
- Interfaces del sistema (internas / externas)
- Modelo de datos / estructura de datos
- Seguridad: autenticación, autorización, manejo de datos sensibles
- Escalabilidad y rendimiento
- Infraestructura y despliegue (entornos, CI/CD, monitoreo, etc.)
- Mantenibilidad / extensibilidad
- Plan de pruebas / validación
- Matriz de trazabilidad de requerimientos

---

## 8. Apéndices (si aplica)

- Mockups, prototipos, diagramas adicionales
- Decisiones de diseño importantes y alternativas consideradas
- Documentación de referencia

---

## 9. Revisión y mantenimiento del documento

### Historial de Revisión / Mantenimiento

| Versión | Fecha | Autor(es) | Cambios Realizados | Aprobado por / Revisor principal | Comentarios adicionales |
| --- | --- | --- | --- | --- | --- |
| 0.1 | 2025-09-23 | Clemente Labrador
Emilio Macial | Creación inicial del documento; estructura básica establecida
 | Nombre del revisor inicial | Primer borrador |
| 0.2 | 2025-09-24 | Clemente Labrador | Adición de requerimientos no funcionales; ajuste al caso de uso | Revisor(es) | Feedback de equipo/profesor |
| 0.3 | YYYY-MM-DD | Autor(es) otra modificación | Incorporación de diagramas VUI; mejora de flujos de voz | Revisor principal | Versiones de diagramas revisadas |
| 1.0 | YYYY-MM-DD | Autor(es) final(es) | Documento aprobado para uso / entrega final | Nombre del aprobador | Versión oficial para implementación |
