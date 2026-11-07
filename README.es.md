# Haier SmartAir2 con compatibilidad V3 Cloud — fork comunitario

Este repositorio extiende [la integración original de bwitosze](https://github.com/bwitosze/haier-smartair2-cloud-for-homeassistant) para equipos SmartAir2 V3 que funcionan mediante MQTT en la nube de Haier (no hOn).

**Estado: beta.** En un equipo MK-QTWIFI08 hemos comprobado temperatura, apagado/encendido, los cinco modos, velocidades del ventilador, oscilaciones vertical/horizontal y purificación. Otros modelos V3 y una instalación completamente nueva todavía requieren validación física.

## Uso desde HACS

1. Crea un **fork** en GitHub del repositorio original.
2. Copia el contenido del ZIP de ampliación a la raíz de tu fork (conservando `.git/` y `LICENSE`).
3. Ejecuta `python scripts/configure_fork.py --github-user TU_USUARIO`.
4. Haz commit/push y crea una versión de prueba cuando termines las comprobaciones.
5. En Home Assistant → HACS → repositorios personalizados, añade `https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine`, tipo **Integration**.
6. Instala, reinicia Home Assistant, añade la integración Haier SmartAir2 y accede con tu cuenta de la aplicación SmartAir2.

La integración descubre los dispositivos de la cuenta automáticamente. Para cada V3 cloud crea controles independientes de oscilación vertical, horizontal y Purificar; solo están disponibles cuando el equipo comunica los atributos correspondientes.

**Limitación importante:** después de reiniciar puede faltar el estado inicial MQTT. Los cambios de modo/temperatura/velocidad se bloquean hasta recibir un conjunto completo de atributos; el encendido utiliza un comando individual. No se inventan valores de los atributos restantes.

No instales el fork y la integración original a la vez: ambas utilizan el dominio `haier_smartair2`. Haz una copia de seguridad antes de actualizar, y conserva el archivo `LICENSE` MIT original.

Consulta la [documentación completa en inglés](README.md), [compatibilidad](COMPATIBILITY.md) y [desarrollo/publicación](DEVELOPMENT.md).
