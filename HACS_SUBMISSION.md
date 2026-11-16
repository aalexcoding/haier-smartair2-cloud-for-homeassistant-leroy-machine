# Solicitud de inclusión en HACS (`hacs/default`)

Repositorio: **`aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine`**
URL: <https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine>
Categoría HACS: **Integration** · Dominio: `haier_smartair2`

Documentación de referencia (consultada el 2026-11-17):

- <https://hacs.xyz/docs/publish/start>
- <https://hacs.xyz/docs/publish/integration>
- <https://hacs.xyz/docs/publish/include>
- <https://hacs.xyz/docs/publish/action>
- <https://contributors.home-assistant.io/core/integrations/manifest/>
- <https://contributors.home-assistant.io/blog/2026/02/24/brands-proxy-api/>

## 1. Requisitos comprobados

| Requisito | Estado | Cómo se comprobó |
| --- | --- | --- |
| Repositorio público en GitHub | OK | API pública de GitHub |
| Descripción del repositorio | OK (mejorable, ver §2) | API pública de GitHub |
| Licencia identificable por GitHub (MIT) | OK | API pública de GitHub (`spdx_id: MIT`) |
| No archivado | OK | API pública de GitHub |
| Una sola integración en `custom_components/haier_smartair2/` | OK | Inspección local |
| `hacs.json` con `name` y solo claves documentadas | OK | Se eliminó `render_readme`, que no figura en la documentación actual |
| `manifest.json` con `domain`, `name`, `version`, `documentation`, `issue_tracker`, `codeowners` | OK | Inspección local |
| `version` válida para AwesomeVersion | OK | `0.2.1` (SemVer); coincide con el tag de la próxima release |
| `categories` válida (`climate.heat_pumps_air_conditioning`) | OK | Documentación de HA; hassfest no informa de errores ni avisos en esta clave |
| Icono de marca local `brand/icon.png` (256×256) y `brand/icon@2x.png` (512×512) | OK | `magick identify` |
| Workflow HACS (`hacs/action@main`, `category: integration`) | Creado | Ver §2: falta que pase en GitHub |
| Workflow hassfest (`home-assistant/actions/hassfest@master`) | Creado | Ver §2: falta que pase en GitHub |
| Sin conflicto de dominio con integraciones del núcleo | OK | hassfest local no informa de conflicto |
| Upstream `bwitosze/haier-smartair2-cloud-for-homeassistant` en `hacs/default` | No figura | Lectura parcial de la lista `integration`; la posición alfabética donde iría está vacía |

## 2. Requisitos pendientes (bloqueantes)

1. **Activar Issues en GitHub.** Ahora mismo están desactivados (`has_issues: false`, como ocurre por defecto en los forks). La comprobación `issues` de HACS falla y el enlace `issue_tracker` del manifest devuelve 404.
   *Settings → General → Features → Issues.*
2. **Añadir topics.** Ahora no hay ninguno. Propuesta:
   `home-assistant`, `homeassistant`, `hacs`, `hacs-integration`, `home-assistant-integration`, `haier`, `smartair2`, `air-conditioner`, `climate`, `mqtt`.
3. ~~Corregir el error de hassfest sobre `requirements`~~ **Hecho:** `paho-mqtt>=2.1.0`.
4. **Hacer push y comprobar que las tres GitHub Actions pasan** (`HACS validation`, `Validate with hassfest`, `Python protocol checks`) **sin** el parámetro `ignore`.
5. **Crear una GitHub Release completa** después de que pasen las Actions (ver §5).
6. **(Recomendado) Mejorar la descripción del repositorio.** La actual menciona "Haier Tundra Plus" y Leroy Merlin. Propuesta:
   *"Home Assistant integration for Haier air conditioners on the legacy SmartAir2 cloud, including V3 (MK-QTWIFI08) devices."*

## 3. Entrada que debe añadirse al catálogo

Archivo **`integration`** de `hacs/default` (array JSON), insertada en **orden alfabético** (sin distinguir mayúsculas), no al final. A fecha 2026-11-17 va entre `"aaamoeder/ha-goboony",` y `"aarikmudgal/ha-speedport-smart",`:

```json
  "aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine",
```

## 4. Enlaces que deben aportarse en la PR

- Release actual: `https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/releases/tag/<TAG>`
- Ejecución correcta de la acción HACS: `https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/runs/<RUN_ID>`
- Ejecución correcta de hassfest: `https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/runs/<RUN_ID>`

## 5. Versionado y GitHub Release

**Situación real:**

- En GitHub existe la release **`0.1.0`** ("Stable", publicada el 2026-11-10). Su tag apunta a `aa8d3b6`, el mismo commit que el `HEAD` local actual.
- En ese commit, `manifest.json` declara **`0.2.0-beta.1`** y `CHANGELOG.md` dice "0.2.0-beta.1 — candidate, not published".
- Por tanto, quien instala la release `0.1.0` desde HACS recibe un código que Home Assistant muestra como `0.2.0-beta.1`. Los usuarios ven dos versiones distintas para el mismo código.
- El tag `0.1.0` no existe en el clon local (no se ha hecho `git fetch --tags`).

**Decisión tomada:** publicar la release estable **`0.2.1`**.

- `manifest.json` ya declara `"version": "0.2.1"` y el CHANGELOG tiene la sección `0.2.1`.
- El tag debe ser exactamente `0.2.1`, sin prefijo `v`, igual que la release existente `0.1.0`.
- `0.2.1 > 0.1.0`, así que quien tenga `0.1.0` recibirá la actualización en HACS.
- No borres la release `0.1.0`. Puedes editar sus notas para indicar que contiene el código `0.2.0-beta.1`.

**Pasos para crear la release (manuales):**

```bash
git switch main
git pull
# con los cambios ya en main y las Actions en verde:
git tag -a 0.2.1 -m "0.2.1"
git push origin 0.2.1
```

Después, en GitHub ve a **Releases → Draft a new release**, elige el tag `0.2.1`, pon como título `0.2.1`, pega las notas del CHANGELOG y pulsa **Publish release**. Debe ser una release completa: no basta con el tag.

## 6. Pull Request a `hacs/default`

1. Haz un fork de <https://github.com/hacs/default> **desde tu cuenta personal**, no desde una organización: la PR debe ser editable por los mantenedores.
2. Crea una rama nueva desde `master`, por ejemplo `add-haier-smartair2`.
3. Añade la entrada del §3 al archivo `integration` en orden alfabético.
4. Abre la PR rellenando la plantilla completa. No solicites revisores: la plantilla indica que la PR se cerrará si lo haces.

**Título:**

```text
Adds new integration [aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine]
```

**Descripción (plantilla de `hacs/default`):**

```markdown
## Checklist

- [x] I've read the [publishing documentation](https://hacs.xyz/docs/publish/start).
- [x] I've added the [HACS action](https://hacs.xyz/docs/publish/action) to my repository.
- [x] (For integrations only) I've added the [hassfest action](https://developers.home-assistant.io/blog/2020/04/16/hassfest/) to my repository.
- [x] The actions are passing without any disabled checks in my repository.
- [x] I've added a link to the action run on my repository below in the links section.
- [x] I've created a new release of the repository after the validation actions were run successfully.

## Links

Link to current release: https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/releases/tag/0.2.1
Link to successful HACS action (without the `ignore` key): https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/runs/<RUN_ID>
Link to successful hassfest action (if integration): https://github.com/aalexcoding/haier-smartair2-cloud-for-homeassistant-leroy-machine/actions/runs/<RUN_ID>
```

Marca cada casilla solo cuando se haya cumplido de verdad. HACS cierra sin aviso las PR con la plantilla mal rellenada.

## 7. Riesgos para la revisión

- **El repositorio es un fork de GitHub** (`bwitosze/haier-smartair2-cloud-for-homeassistant`). La documentación de HACS consultada no prohíbe los forks, pero exige que quien envía sea el propietario o un colaborador principal del repositorio. Los créditos al autor original se mantienen en el README.
- **Dominio compartido con upstream** (`haier_smartair2`). Si el proyecto original se añadiera al catálogo, habría dos entradas con el mismo dominio. Los README advierten de que no deben instalarse a la vez.
- **Plazo de revisión:** la documentación de HACS indica que las inclusiones nuevas pueden tardar meses en revisarse.
