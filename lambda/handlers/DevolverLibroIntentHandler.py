class DevolverLibroIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("DevolverLibroIntent")(handler_input)

    def handle(self, handler_input):
        try:
            titulo = ask_utils.get_slot_value(handler_input, "titulo")
            id_prestamo = ask_utils.get_slot_value(handler_input, "id_prestamo")

            if not titulo and not id_prestamo:
                prompts = [
                    "¡Qué bien! ¿Qué libro te devolvieron?",
                    "Perfecto, vamos a registrar la devolución. ¿Cuál libro es?",
                    "¡Excelente! ¿Qué libro estás devolviendo?"
                ]
                return (
                    handler_input.response_builder
                        .speak(random.choice(prompts))
                        .ask("¿Cuál es el título del libro?")
                        .response
                )

            user_data = DatabaseManager.get_user_data(handler_input)
            prestamos = user_data.get("prestamos_activos", [])

            if not prestamos:
                speak_output = "No tienes libros prestados en este momento. Todos tus libros están en su lugar. "
                speak_output += get_random_phrase(ALGO_MAS)
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )

            prestamo_encontrado = None
            indice = -1

            for i, p in enumerate(prestamos):
                if id_prestamo and p.get("id") == id_prestamo:
                    prestamo_encontrado = p
                    indice = i
                    break
                elif titulo and titulo.lower() in (p.get("titulo", "").lower()):
                    prestamo_encontrado = p
                    indice = i
                    break

            if not prestamo_encontrado:
                # Ayudar al usuario listando préstamos
                if len(prestamos) == 1:
                    p = prestamos[0]
                    sugerencia = f"Solo tienes prestado '{p.get('titulo')}' a {p.get('persona')}. ¿Es ese?"
                else:
                    titulos_prestados = [f"'{p.get('titulo')}'" for p in prestamos[:3]]
                    sugerencia = f"Tienes prestados: {', '.join(titulos_prestados)}. ¿Cuál de estos es?"
                
                return (
                    handler_input.response_builder
                        .speak(f"Hmm, no encuentro ese libro en los préstamos. {sugerencia}")
                        .ask("¿Cuál libro quieres devolver?")
                        .response
                )

            # Procesar devolución
            prestamos.pop(indice)
            prestamo_encontrado["fecha_devolucion"] = datetime.now().isoformat()
            prestamo_encontrado["estado"] = "devuelto"

            # Calcular si fue devuelto a tiempo
            fecha_limite = datetime.fromisoformat(prestamo_encontrado["fecha_limite"])
            devuelto_a_tiempo = datetime.now() <= fecha_limite

            historial = user_data.get("historial_prestamos", [])
            historial.append(prestamo_encontrado)

            libros = user_data.get("libros_disponibles", [])
            for l in libros:
                if l.get("id") == prestamo_encontrado.get("libro_id"):
                    l["estado"] = "disponible"
                    break

            user_data["prestamos_activos"] = prestamos
            user_data["historial_prestamos"] = historial
            stats = user_data.get("estadisticas", {})
            stats["total_devoluciones"] = stats.get("total_devoluciones", 0) + 1

            DatabaseManager.save_user_data(handler_input, user_data)

            # Respuesta natural
            confirmacion = get_random_phrase(CONFIRMACIONES)
            speak_output = f"{confirmacion} He registrado la devolución de '{prestamo_encontrado['titulo']}'. "
            
            if devuelto_a_tiempo:
                speak_output += "¡Fue devuelto a tiempo! "
            else:
                speak_output += "Fue devuelto un poco tarde, pero no hay problema. "
            
            speak_output += "Espero que lo hayan disfrutado. "
            
            if prestamos:
                speak_output += f"Aún tienes {len(prestamos)} "
                speak_output += "libro prestado. " if len(prestamos) == 1 else "libros prestados. "
            
            speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error en DevolverLibro: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Tuve un problema registrando la devolución. ¿Lo intentamos de nuevo?")
                    .ask("¿Qué libro quieres devolver?")
                    .response
            )
