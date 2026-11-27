# Auditoría y plan técnico de Elegan-backend para 500.000 usuarios activos diarios

**Fecha:** 2026-11-26  
**Repositorio:** `carlos02200375720/Elegan-backend`  
**Rama auditada:** `main`  
**Commit base de la auditoría:** `6463c49f4afd8870fe7b6a6371af0d3dda68f405`

## 1. Alcance y límites

Esta revisión es una auditoría estática inicial del código disponible en GitHub. No se modificó código de ejecución, configuración de Cloud Run, MongoDB ni recursos de Google Cloud. No se ejecutaron pruebas unitarias, pruebas de integración ni pruebas de carga. La ausencia de resultados de estado en GitHub para el commit revisado no demuestra que el código haya pasado CI.

Los objetivos de 500.000 usuarios activos diarios, 2.000 solicitudes API/s y 50.000 conexiones WebSocket simultáneas son metas de diseño, no capacidades verificadas.

## 2. Arquitectura actual observada

- Aplicación backend: FastAPI en un único servicio.
- Persistencia: MongoDB Atlas mediante PyMongo síncrono.
- Multimedia: Google Cloud Storage; los comprobantes usan un bucket privado separado.
- Ejecución: Docker y Cloud Run.
- Tiempo real: WebSockets dentro del proceso FastAPI y MongoDB Change Streams.
- Tareas multimedia: colección MongoDB `media_tasks`, reclamada atómicamente; se activa mediante `BackgroundTasks` de FastAPI.
- Observabilidad: Sentry está integrado con muestreo de trazas configurado en 10%.
- Eventos distribuidos, Pub/Sub, Cloud Tasks, CDN y un proceso worker independiente: no aparecen implementados en los archivos revisados.

## 3. Hallazgos prioritarios

### P0 — Resolver antes del siguiente despliegue

**Destino de despliegue no coincidente.** El workflow `.github/workflows/deploy.yml` declara `SERVICE_NAME=elegan-backend` y `REGION=us-east1`. El servicio que el propietario había identificado como backend vigente es `backend-elegan-rd` en `us-central1`. Debe verificarse el destino real antes de ejecutar otro despliegue. No cambiar variables hasta confirmar el servicio correcto.

**Tiempo real no distribuido entre instancias.** `backend/rutas/eventos.py` mantiene los sockets en memoria local y recorre secuencialmente las conexiones para enviar cada evento y heartbeat. Cada instancia abre su propio Change Stream. No hay canal compartido que entregue a cada gateway los eventos de los clientes conectados a esa instancia. Escalar Cloud Run horizontalmente no resuelve por sí solo esta distribución.

**Cola multimedia sin trabajador independiente.** `backend/logica/tareas_multimedia.py` persiste tareas, aplica intentos y leases, pero las rutas llaman al procesador mediante `BackgroundTasks` en la misma instancia API. Si la instancia termina antes de procesar una tarea, esta queda pendiente hasta que otra operación vuelva a activar el procesador. FFmpeg también consume CPU y disco temporal del servicio API.

**Limpieza multimedia potencialmente costosa.** `eliminar_referencias_multimedia_sin_uso` recorre todas las colecciones devueltas por MongoDB y ejecuta una búsqueda por colección antes de borrar. El límite de 750 ms se aplica a cada consulta, no al recorrido completo. Con más colecciones y datos, esta operación puede acumular latencia y carga.

### P1 — Corregir antes de pruebas de capacidad

**Escrituras amplificadas en conversaciones.** En `backend/logica/mensajes.py`, cada mensaje nuevo ejecuta `update_many` sobre todos los mensajes del usuario para renovar `expiresAt`. El costo de escribir un mensaje crece con el tamaño de la conversación. Se debe evaluar un documento de conversación con actividad/expiración propia y una política de retención que no requiera reescribir el historial.

**Consultas N+1 del carrito.** `obtener_carrito` recupera los elementos y después ejecuta una consulta de producto por cada elemento. Debe sustituirse por una lectura agrupada de productos, conservando el mismo contrato de respuesta.

**Pool MongoDB sin límites explícitos de aplicación.** `create_mongodb_client` configura timeouts de conexión y selección, pero no declara límites explícitos de pool, conexiones en espera ni conexiones máximas por proceso. Los límites por instancia deben definirse y calcularse junto con el máximo de instancias de Cloud Run y el límite global de MongoDB Atlas.

**Health check superficial.** `/health` devuelve `status=ok` sin comprobar MongoDB ni dependencias. Deben existir comprobaciones separadas de liveness y readiness; readiness debe comprobar la disponibilidad necesaria para atender tráfico sin filtrar secretos ni datos privados.

**Autenticación y sesiones.** Los JWT observados tienen una duración de siete días. Los endpoints de logout responden sin revocar tokens en el backend. La meta de tokens más cortos, renovación y revocación necesita diseño compatible con las sesiones móviles actuales antes de cambiar el contrato.

**Protección de entrada.** En el arranque de FastAPI revisado no se observa un limitador de solicitudes por usuario/IP. Debe diseñarse en la capa de entrada o middleware con límites distintos para login, recuperación, catálogo, escritura y administración.

### P2 — Estructura y mantenimiento

La regla solicitada es máximo 200 líneas por archivo de código fuente. En la revisión se midieron estos archivos:

| Archivo | Líneas observadas |
|---|---:|
| `backend/main.py` | 249 |
| `backend/logica/media.py` | 350 |
| `backend/logica/autenticacion.py` | 314 |
| `backend/logica/productos.py` | 214 |
| `backend/logica/mensajes.py` | 204 |
| `backend/logica/checkout.py` | 206 |

La división debe hacerse por responsabilidad y con pruebas de regresión. No se deben mover funciones de forma masiva ni cambiar nombres de endpoints o contratos solo para reducir líneas.

## 4. Componentes que ya existen y deben conservarse

- Rutas de negocio móvil y administración bajo `/api/movil` y `/api/admin`.
- Autenticación JWT diferenciada por audiencia móvil/administración.
- Paginación por cursor en catálogo, órdenes y mensajes.
- Transacción MongoDB en checkout con reserva atómica de inventario e idempotencia.
- Colección persistente `checkout_idempotency`.
- Bucket público para multimedia de catálogo y bucket privado para comprobantes.
- Carga multimedia por bloques hacia GCS.
- Cola MongoDB `media_tasks` con reclamación atómica, lease y reintentos.
- Sentry con sanitización de datos sensibles antes del envío.

Estos componentes no deben reemplazarse sin revisar compatibilidad y ejecutar pruebas funcionales.

## 5. Arquitectura objetivo acordada

1. **API comercial modular:** FastAPI en Cloud Run para autenticación, catálogo, carrito, pedidos, pagos y perfiles.
2. **Gateway WebSocket independiente:** servicio Cloud Run separado, con autenticación y autorización por usuario/conversación.
3. **Eventos de negocio:** Pub/Sub para distribuir eventos a consumidores independientes; usar Outbox para evitar que una escritura de negocio quede confirmada sin su evento.
4. **Tareas individuales:** Cloud Tasks para trabajos con destino, reintentos y programación definidos.
5. **Trabajadores independientes:** multimedia, notificaciones y limpieza, escalados por cola y no por conexiones de usuario.
6. **Persistencia:** MongoDB Atlas con índices por consultas reales, límites de conexiones, copias y política de retención.
7. **Multimedia:** flujo Aplicación → API → GCS; procesamiento fuera de la API y CDN para lectura.
8. **Distribución WebSocket entre gateways:** Redis/Memorystore queda expresamente aplazado por decisión de presupuesto. Antes de contratarlo, no se debe afirmar que el gateway está preparado para entregar eventos entre decenas de miles de conexiones distribuidas.
9. **Observabilidad:** Cloud Monitoring, métricas p95/p99, OpenTelemetry, alertas y trazabilidad entre API, eventos y workers.

## 6. Plan de implementación

### Etapa 1 — Estabilizar y medir el backend actual

- Confirmar el servicio/region de despliegue correcto.
- Inventariar rutas, colecciones, índices y consultas.
- Medir pool MongoDB y consumo por instancia.
- Resolver consultas N+1 y escrituras amplificadas.
- Añadir pruebas unitarias e integración para autenticación, carrito, checkout, pagos, mensajes y multimedia.
- Introducir readiness/liveness sin cambiar el contrato funcional de las rutas.
- Dividir archivos mayores de 200 líneas de forma incremental y cubierta por pruebas.

**Aceptación:** suite de pruebas funcionales aprobada; ningún cambio de contrato móvil/admin no autorizado; consultas principales con índices comprobados mediante explain; límites de conexión documentados.

### Etapa 2 — Trabajadores y mensajería asíncrona

- Mantener la cola MongoDB actual como transición, pero añadir recuperación programada real o migrar tareas a Cloud Tasks.
- Crear un proceso de worker separado para FFmpeg, limpieza y notificaciones.
- Introducir Pub/Sub para eventos de negocio y Outbox transaccional.
- Definir idempotencia de cada consumidor, DLQ/estado terminal y métricas de retraso.
- Asegurar que la API solo valide, almacene y encole; no procese vídeos después de responder.

**Aceptación:** detener una instancia API no pierde tareas; reintentos no duplican efectos; el worker escala sin aumentar instancias de API; limpieza nunca borra objetos referenciados.

### Etapa 3 — Tiempo real escalable

- Extraer el gateway WebSocket del proceso API.
- Separar almacenamiento de mensajes de entrega de eventos.
- Añadir Outbox y publicación durable.
- Implementar reconexión, backoff, cursor de sincronización y recuperación de eventos.
- Probar primero distribución con el mecanismo compartido seleccionado. Redis/Memorystore permanece pendiente de autorización presupuestaria.

**Aceptación:** mensajes confirmados persisten; clientes recuperan mensajes tras desconexión; autorización por usuario/conversación; pruebas de distribución multiinstancia; medición de conexiones por instancia.

### Etapa 4 — Capacidad y costos

- Configurar límites y concurrencia de Cloud Run mediante pruebas.
- Ajustar MongoDB Atlas y el presupuesto global de conexiones.
- Añadir CDN y métricas de transferencia GCS.
- Configurar alertas de costos, cuotas, errores y saturación.
- Probar restauración y recuperación ante fallos.

### Etapa 5 — Validación de objetivos

Pruebas progresivas: 5.000, 10.000, 25.000 y 50.000 conexiones; objetivo API de 2.000 solicitudes/s bajo un perfil de tráfico definido. Medir p50/p95/p99, errores, CPU, memoria, pool MongoDB, lag de eventos, cola, transferencia y costo. La reserva de 100.000 conexiones requiere una campaña específica posterior.

## 7. Reglas de seguridad para los cambios

- Trabajar directamente sobre `main`, sin crear ramas ni PR salvo solicitud expresa.
- No desplegar ni modificar infraestructura sin autorización expresa.
- No añadir Redis/Memorystore ahora.
- No modificar endpoints, modelos de respuesta ni lógica comercial sin pruebas de compatibilidad.
- No eliminar ni migrar colecciones/archivos sin un plan de reversión.
- Cada cambio debe indicar archivos afectados, pruebas ejecutadas y resultado real.
- No declarar capacidad de producción a partir de estimaciones o de un build exitoso.

## 8. Próximas acciones recomendadas

1. Confirmar el destino correcto del workflow antes de cualquier despliegue.
2. Completar inventario de rutas, colecciones, índices y archivos de todo el repositorio.
3. Añadir/ejecutar pruebas de regresión de los flujos existentes.
4. Corregir primero las escrituras amplificadas de mensajes y la consulta N+1 del carrito.
5. Diseñar el worker multimedia independiente sin introducir Redis.
