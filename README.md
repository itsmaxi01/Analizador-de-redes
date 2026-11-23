# Network Graph Analyzer

Simulador local de infraestructura empresarial implementado en Python 3.12+. Permite administrar dispositivos y enlaces físicos, registrar su salud, analizar conectividad física y operativa, ejecutar consultas mediante un lenguaje formal y visualizar la topología actual.

## Funcionalidades

- Dispositivos Router, Switch, PC y Server con IPv4 privada única.
- Enlaces físicos simples, bidireccionales y sin peso.
- Diagnóstico NORMAL, WARNING o FAILURE mediante eventos R/T.
- Caminos mínimos, grados, aislamiento y componentes conexos.
- Diagnóstico detallado de interrupciones de comunicación.
- Carga atómica desde archivos UTF-8.
- Lenguaje formal con lexer, parser LL(1), AST e intérprete.
- Consola interactiva con sesión persistente.
- Visualización de topología y salud con NetworkX y Matplotlib.

## Estructura

```text
core/               Dominio, validadores, AFD, grafos, carga y sesión
language/           Lexer, parser LL(1), AST y evaluador semántico
data/               Infraestructura cargada por CARGAR()
tests/              Pruebas unitarias y de integración
main.py             Interfaz de consola
visualization.py    Construcción, presentación y guardado de figuras
```

`core` no depende de la capa de lenguaje. La CLI y la visualización consumen los contratos públicos del evaluador y no duplican reglas del dominio ni algoritmos de grafos.

## Instalación

Crear y activar un entorno virtual:

```console
python -m venv .venv
.venv\Scripts\activate
```

Instalar las dependencias:

```console
python -m pip install -r requirements.txt
```

## Ejecutar la CLI

Desde la raíz del proyecto:

```console
python main.py
```

Ejemplo:

```text
Network Graph Analyzer. Escribe SALIR para terminar.
nga> CARGAR()
Carga completada: 7 dispositivos, 6 conexiones.
nga> SALUD(Switch1)
Switch1: diagnóstico=FAILURE, operativo=no
nga> CAMINO(PC1,Server1,FISICA)
Ruta: PC1 -> Switch1 -> Switch2 -> Server1 (3 saltos)
nga> OPERATIVO(PC1)
Verdadero
nga> SALIR
Hasta luego.
```

La misma instancia de sesión se conserva entre instrucciones. Los errores conocidos se muestran sin cerrar el programa. `SALIR` pertenece exclusivamente a la consola y no forma parte de la gramática formal.

## Lenguaje

Las 21 construcciones disponibles son:

```text
CARGAR              REGISTRAR            CAMBIAR_IP
CONECTAR             DESCONECTAR          EVENTO
SALUD                ESTADOS              CAMINO
DIAGNOSTICAR         GRADO                AISLADOS
COMPONENTES          DISPOSITIVOS         CONEXIONES
VISUALIZAR           OPERATIVO            ES_ESTADO
RUTA                 Y                    O
```

La sintaxis es sensible a mayúsculas. Ejemplos:

```text
REGISTRAR(PC4,192.168.1.20,R)
EVENTO(Switch1,R)
RUTA(PC1,Server1,OPERATIVA)
Y(OPERATIVO(PC1),ES_ESTADO(Server1,WARNING))
```

## Datos de carga

`CARGAR()` utiliza los siguientes archivos:

- `data/devices.txt`
- `data/connections.txt`
- `data/events.txt`

Una carga inválida se rechaza íntegramente y conserva la infraestructura anterior.

## Visualización

`VISUALIZAR()` abre una figura no bloqueante con todos los dispositivos y conexiones físicas:

- NORMAL: verde.
- WARNING: amarillo.
- FAILURE: rojo.
- Los enlaces permanecen visibles aunque un dispositivo esté en FAILURE.
- Los dispositivos aislados también aparecen.

La figura puede construirse con `build_figure()`, mostrarse con `show_figure()` o guardarse como PNG mediante `save_figure()`.

## Pruebas

```console
python -m pytest -q
```

La suite cubre dominio, validación, AFD, grafos, carga atómica, sesión, lexer, parser, evaluador, CLI y visualización sin ventanas reales.

## Alcance

Este MVP no realiza pings reales ni implementa IPv6, VLAN, protocolos de enrutamiento, base de datos, autenticación o persistencia adicional.
