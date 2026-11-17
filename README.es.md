# Haier SmartAir2 con compatibilidad V3 Cloud — fork comunitario

[![Validación HACS](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/workflows/hacs.yaml/badge.svg)](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/workflows/hacs.yaml)
[![hassfest](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/workflows/hassfest.yaml)
[![Licencia: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Este repositorio extiende [la integración original de bwitosze](https://github.com/bwitosze/haier-smartair2-cloud-for-homeassistant) para controlar desde Home Assistant aires acondicionados Haier vinculados a la **antigua aplicación SmartAir2** (no hOn), incluidos equipos **SmartAir2 V3** que funcionan mediante MQTT en la nube de Haier. Se conservan los transportes originales V2 Cloud (EPP sobre MQTT) y local (TCP `56800`).

> [!IMPORTANT]
> **Integración comunitaria no oficial.** Este proyecto no está afiliado, respaldado ni soportado por Haier. Utiliza interfaces de nube no documentadas que pueden cambiar en cualquier momento. Úsalo bajo tu responsabilidad.

**Estado: beta.** En un equipo MK-QTWIFI08 hemos comprobado temperatura, apagado/encendido, los cinco modos, velocidades del ventilador, oscilaciones vertical/horizontal y purificación. Otros modelos V3 y una instalación completamente nueva todavía requieren validación física.

## Qué hace

- Crea una entidad `climate` y un sensor de temperatura interior por cada equipo.
- Descubre automáticamente los dispositivos asociados a tu cuenta SmartAir2.
- **V3 Cloud:** encendido/apagado, temperatura objetivo, modos `auto`, `cool`, `heat`, `dry`, `fan_only` y ventilador `auto / low / medium / high`.
- Para cada equipo V3 cloud crea interruptores independientes de oscilación vertical, oscilación horizontal y **Purificar**; solo funcionan cuando el equipo comunica los atributos correspondientes.

## Dispositivos compatibles

| Generación / transporte | Estado |
| --- | --- |
| V2 Cloud | Soporte original conservado; se agradecen pruebas de regresión. |
| V3 Local | Soporte experimental original conservado (TCP `56800`); no todos los módulos lo admiten. |
| V3 Cloud — MK-QTWIFI08 | **Probado en hardware real.** |
| Otros V3 Cloud | **Experimental**; los atributos varían según el modelo. |

Detalles en [COMPATIBILITY.md](COMPATIBILITY.md). No se garantiza que todos los equipos V3 admitan todas las funciones.

## Requisitos

- Home Assistant **2025.1.0** o posterior (los iconos de marca locales se muestran a partir de 2026.3).
- [HACS](https://hacs.xyz/) / Marketplace de Home Assistant para la instalación recomendada.
- Una cuenta de la **antigua aplicación SmartAir2** (no hOn) con los equipos ya emparejados.
- Acceso a Internet desde Home Assistant hacia la nube de Haier.

## Instalación

### Marketplace / HACS (recomendada)

[![Abre tu instancia de Home Assistant y muestra este repositorio en el Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=aalexcoding&repository=haier-smartair2-cloud-for-homeassistant-leroy-machine&category=integration)

1. Pulsa el botón anterior, o abre el **Marketplace** (HACS) en Home Assistant y busca **Haier SmartAir2 (V3 cloud support)**.
   - Mientras el repositorio no esté incluido en el catálogo por defecto de HACS, añádelo antes como **repositorio personalizado** (menú de tres puntos → **Repositorios personalizados**), tipo **Integration**:

     ```text
     https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine
     ```

2. Descarga la integración.
3. Reinicia Home Assistant.

> **¿Ya usas la integración original?** Ambas utilizan el dominio `haier_smartair2`. **No** instales el fork y la integración original a la vez. Haz una copia de seguridad antes de actualizar, sustituye el código desde HACS y reinicia. No borres la entrada de la integración ni las entidades salvo que quieras reconfigurarlas.

### Instalación manual

1. Descarga la última [release](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/releases) (o clona el repositorio).
2. Copia `custom_components/haier_smartair2/` en `<config>/custom_components/` de Home Assistant.
3. Reinicia Home Assistant. Usa una sola copia de este dominio.

### Actualización

- **HACS / Marketplace:** cuando se publique una nueva release, Home Assistant mostrará la actualización. Instálala y reinicia.
- **Manual:** sustituye el directorio `custom_components/haier_smartair2/` completo y reinicia.
- Revisa el [CHANGELOG](CHANGELOG.md) antes de actualizar. La entrada de configuración y las entidades se conservan.

## Configuración inicial

[![Abre tu instancia de Home Assistant y empieza a configurar Haier SmartAir2.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=haier_smartair2)

1. Ve a **Ajustes → Dispositivos y servicios → Añadir integración → Haier SmartAir2 (V3 cloud support)**.
2. Introduce el correo y la contraseña de tu cuenta SmartAir2 y selecciona la región (solo se ha probado Europa).
3. Opcionalmente, asocia equipos a una IP local (`MAC:IP`, separados por comas) para el transporte local.

Puedes cambiar la región y las asociaciones locales en las opciones de la integración. Cambiar de transporte puede afectar a los identificadores de entidad.

Si Haier rechaza la contraseña, la integración detiene los intentos automáticos de inicio de sesión. Abre **Ajustes → Dispositivos y servicios** y sigue el aviso de reautenticación para introducir tu contraseña actual de SmartAir2. Se conservan los dispositivos y los ajustes. Los fallos temporales de conexión se reintentan con intervalos crecientes, hasta cinco minutos.

## Limitaciones conocidas

- **Estado inicial:** después de reiniciar puede faltar el estado inicial MQTT. Los cambios de modo/temperatura/velocidad se bloquean hasta recibir un conjunto completo de atributos; el encendido utiliza un comando individual. No se inventan valores de los atributos restantes.
- **Dependencia de la nube:** cambios en el servicio de Haier pueden afectar al funcionamiento.
- **Regiones:** solo se ha probado la nube europea.
- **TLS:** todas las conexiones a la nube (inicio de sesión, descubrimiento del gateway y MQTT) verifican el certificado y el nombre del servidor. Si los gateways `us` o `sg` presentasen un certificado no válido, la conexión fallará con un error TLS en lugar de continuar sin verificación; por favor, notifícalo. El transporte **local** (TCP `56800`) no cifra por diseño del protocolo del dispositivo.
- **Sin soporte hOn** ni para la API de la nube de China continental.

## Incidencias

Comunica errores y resultados de compatibilidad en **[GitHub Issues](https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/issues)**. **Nunca publiques** credenciales, tokens de acceso, topics MQTT completos con tokens ni identificadores de dispositivo sin anonimizar.

## Créditos y licencia

Basado en el trabajo de [bwitosze](https://github.com/bwitosze/haier-smartair2-cloud-for-homeassistant); extensión V3 Cloud por [Alejandro Delgado (@aalexcoding)](https://github.com/aalexcoding). Distribuido bajo la [licencia MIT](LICENSE) original, que debe conservarse.

Consulta la [documentación completa en inglés](README.md), [compatibilidad](COMPATIBILITY.md) y [desarrollo/publicación](DEVELOPMENT.md).
