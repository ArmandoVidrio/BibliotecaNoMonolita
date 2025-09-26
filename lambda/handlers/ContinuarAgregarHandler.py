class ContinuarAgregarHandler(AbstractRequestHandler):
    """Handler para continuar el proceso de agregar cuando el usuario responde"""
    def can_handle(self, handler_input):
        session_attrs = handler_input.attributes_manager.session_attributes
        # Solo manejar si estamos agregando Y no es el intent de agregar
        return (session_attrs.get("agregando_libro") and 
                not ask_utils.is_intent_name("AgregarLibroIntent")(handler_input) and
                not ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) and
                not ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input))
    
    def handle(self, handler_input):
        try:
            session_attrs = handler_input.attributes_manager.session_attributes
            esperando = session_attrs.get("esperando")
            
            # Intentar obtener el valor de la respuesta
            valor = None
            request = handler_input.request_envelope.request
            
            if hasattr(request, 'intent') and request.intent:
                intent_name = request.intent.name if hasattr(request.intent, 'name') else None
                logger.info(f"Intent detectado: {intent_name}")
                
                # Primero, buscar el slot 'respuesta' del RespuestaGeneralIntent
                if intent_name == "RespuestaGeneralIntent":
                    valor = ask_utils.get_slot_value(handler_input, "respuesta")
                    logger.info(f"Respuesta general capturada: {valor}")
                
                # Si no es RespuestaGeneralIntent, buscar en cualquier slot disponible
                if not valor and hasattr(request.intent, 'slots') and request.intent.slots:
                    for slot_name, slot in request.intent.slots.items():
                        if slot and hasattr(slot, 'value') and slot.value:
                            valor = slot.value
                            logger.info(f"Valor encontrado en slot {slot_name}: {valor}")
                            break
                
                # IMPORTANTE: Para intents mal interpretados, intentar capturar el utterance original
                # Esto es un workaround cuando Alexa malinterpreta la respuesta
                if not valor and intent_name in ["LimpiarCacheIntent", "SiguientePaginaIntent", 
                                                 "ListarLibrosIntent", "BuscarLibroIntent"]:
                    # Cuando el usuario dice algo que Alexa malinterpreta,
                    # pedimos que repita con una frase más específica
                    if esperando == "autor":
                        return (
                            handler_input.response_builder
                                .speak("No entendí bien. Por favor di: 'el autor es' seguido del nombre. O di: no sé el autor.")
                                .ask("¿Quién es el autor? Di: 'el autor es' y el nombre.")
                                .response
                        )
                    elif esperando == "tipo":
                        return (
                            handler_input.response_builder
                                .speak("No entendí bien. Por favor di: 'el tipo es' seguido del género. O di: no sé el tipo.")
                                .ask("¿De qué tipo es? Di: 'el tipo es' y el género.")
                                .response
                        )
                    elif esperando == "titulo":
                        return (
                            handler_input.response_builder
                                .speak("No entendí bien. Por favor di: 'el título es' seguido del nombre del libro.")
                                .ask("¿Cuál es el título? Di: 'el título es' y el nombre.")
                                .response
                        )
            
            logger.info(f"ContinuarAgregar - Esperando: {esperando}, Valor: {valor}")
            
            # Procesar según lo que estamos esperando
            if esperando == "titulo":
                if valor:
                    session_attrs["titulo_temp"] = valor
                    session_attrs["esperando"] = "autor"
                    return (
                        handler_input.response_builder
                            .speak(f"¡'{valor}' suena interesante! ¿Quién es el autor? Si no lo sabes, di: no sé el autor.")
                            .ask("¿Quién es el autor? Puedes decir: 'el autor es' y el nombre, o 'no sé el autor'.")
                            .response
                    )
                else:
                    return (
                        handler_input.response_builder
                            .speak("No entendí el título. Por favor di: 'el título es' seguido del nombre del libro.")
                            .ask("¿Cuál es el título del libro?")
                            .response
                    )
            
            elif esperando == "autor":
                # Manejar variaciones de "no sé"
                if not valor or valor.lower() in ["no sé", "no se", "no lo sé", "no lo se", 
                                                  "no sé el autor", "no se el autor"]:
                    valor = "Desconocido"
                # Limpiar prefijos comunes
                elif valor.lower().startswith("el autor es "):
                    valor = valor[12:].strip()
                elif valor.lower().startswith("es "):
                    valor = valor[3:].strip()
                
                session_attrs["autor_temp"] = valor
                session_attrs["esperando"] = "tipo"
                
                titulo = session_attrs.get("titulo_temp")
                autor_text = f" de {valor}" if valor != "Desconocido" else ""
                
                return (
                    handler_input.response_builder
                        .speak(f"Perfecto, '{titulo}'{autor_text}. ¿De qué tipo o género es? Por ejemplo: novela, fantasía, ciencia ficción. Si no sabes, di: no sé el tipo.")
                        .ask("¿De qué tipo es el libro? Puedes decir: 'el tipo es' y el género, o 'no sé el tipo'.")
                        .response
                )
            
            elif esperando == "tipo":
                # Manejar variaciones de "no sé"
                if not valor or valor.lower() in ["no sé", "no se", "no lo sé", "no lo se",
                                                  "no sé el tipo", "no se el tipo"]:
                    valor = "Sin categoría"
                # Limpiar prefijos comunes
                elif valor.lower().startswith("el tipo es "):
                    valor = valor[11:].strip()
                elif valor.lower().startswith("es "):
                    valor = valor[3:].strip()
                
                # Guardar el libro
                titulo_final = session_attrs.get("titulo_temp")
                autor_final = session_attrs.get("autor_temp", "Desconocido")
                tipo_final = valor
                
                user_data = DatabaseManager.get_user_data(handler_input)
                libros = user_data.get("libros_disponibles", [])
                
                # Verificar duplicado
                for libro in libros:
                    if libro.get("titulo", "").lower() == titulo_final.lower():
                        handler_input.attributes_manager.session_attributes = {}
                        return (
                            handler_input.response_builder
                                .speak(f"'{titulo_final}' ya está en tu biblioteca. " + get_random_phrase(ALGO_MAS))
                                .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                                .response
                        )
                
                nuevo_libro = {
                    "id": generar_id_unico(),
                    "titulo": titulo_final,
                    "autor": autor_final,
                    "tipo": tipo_final,
                    "fecha_agregado": datetime.now().isoformat(),
                    "total_prestamos": 0,
                    "estado": "disponible"
                }
                
                libros.append(nuevo_libro)
                user_data["libros_disponibles"] = libros
                
                stats = user_data.setdefault("estadisticas", {})
                stats["total_libros"] = len(libros)
                
                DatabaseManager.save_user_data(handler_input, user_data)
                
                # Limpiar sesión
                handler_input.attributes_manager.session_attributes = {}
                
                speak_output = f"¡Perfecto! He agregado '{titulo_final}'"
                if autor_final != "Desconocido":
                    speak_output += f" de {autor_final}"
                if tipo_final != "Sin categoría":
                    speak_output += f", categoría {tipo_final}"
                speak_output += f". Ahora tienes {len(libros)} libros en tu biblioteca. "
                speak_output += get_random_phrase(ALGO_MAS)
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )
            
            # Si llegamos aquí, algo salió mal
            handler_input.attributes_manager.session_attributes = {}
            return (
                handler_input.response_builder
                    .speak("Hubo un problema. Empecemos de nuevo. ¿Qué libro quieres agregar?")
                    .ask("¿Qué libro quieres agregar?")
                    .response
            )
            
        except Exception as e:
            logger.error(f"Error en ContinuarAgregar: {e}", exc_info=True)
            handler_input.attributes_manager.session_attributes = {}
            return (
                handler_input.response_builder
                    .speak("Hubo un problema. Intentemos agregar el libro de nuevo.")
                    .ask("¿Qué libro quieres agregar?")
                    .response
            )