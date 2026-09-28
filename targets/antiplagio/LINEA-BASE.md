# Línea base del escenario — 2026-08-31

Valores medidos en **local** (`/var/www/zajuna`), que es `dev` de punta a punta: plugin por bind
mount del repo y analyzer verificado con `md5sum` (26/26 ficheros `.py` idénticos).

Sirve de referencia para el verificador de despliegue: si tras desplegar estos números no
coinciden, el despliegue no reprodujo el sistema.

## Configuración con la que se midió

| | |
|---|---|
| Umbrales | **Alta 10 % · Normal 20 %** (cambiados desde 13 %/15 % el 2026-08-31) |
| Perfil usado | **1 — Alta (10 %)** en las tres evidencias |
| Cotejo web | Desactivado |
| Analyzers | `app0/1/2` como `appuser` (uid 1000) |
| Orden de análisis | EV-C → EV-A → EV-B |

> **No existe perfil «sin umbral».** Se probó (perfil 3, `threshold` 0) y se descartó: tres
> documentos originales y sin relación se reportaban al **1,07 %, 1,07 % y 0,82 %** solo por
> compartir vocabulario común del español. El umbral es lo que separa una coincidencia real del
> ruido de la lengua.

## EV-A · assign 11054 · curso 9864 · 13 entregas

| Aprendiz | % | Qué demuestra |
|---|---|---|
| LUISA FERNANDA HERRERA ALVIAR | 0.00 | Original |
| MILENA DEL CARMEN QUINTERO PEREZ | 0.00 | Original |
| OSWALDO BUENO | 0.00 | Original |
| MONICA ESTHER COGOLLO COGOLLO | 0.00 | Original |
| OSCAR ANDRES OSPINA GIRALDO | 0.00 | Original |
| PAULA ANDREA ARBELAEZ MEJIA | 0.00 | Original |
| NORALBA MONCAYO CHILANGUAY | **0.00** | **Paráfrasis profunda: reescribir con palabras propias NO se reporta** |
| ZEIDA DEL PILAR RAMOS URIBE | **16.46** | Copia literal |
| ROSA MARIA MUÑOZ HERNANDEZ | **16.46** | Copia literal |
| SUSANA VELASQUEZ GIL | **13.81** | Borde: se reporta con Alta (10 %), **no** con Normal (20 %) |
| PAULA ANDREA PALACIOS CORREA | **51.88** | Caso APA |
| SANDRA PATRICIA ROMERO REYES | **51.88** | Caso APA |
| Aprendiz Demo Zajuna | **89.06** | Cruce entre cursos |

**Idénticos a la línea base anterior (13 %).** Bajar el umbral a 10 % no añadió ningún caso
porque no hay pares en la franja 10–13 %. Es la demostración práctica de que **el umbral decide
qué se reporta, no cuánto vale**.

## EV-B · assign 11056 · 5 formatos

`100.00 · 100.00 · 100.00 · **97.66** · 100.00`

> ⚠ **Cambió**: el `.html` (MONICA COGOLLO) pasó de **96.60 a 97.66**. No es efecto del umbral
> —no cambia valores— sino del **almacén de firmas**, que al recalibrar contiene más documentos
> que en la corrida de agosto. Conviene confirmarlo antes de darlo por bueno.

## EV-C · assign 11055 · curso 9860 · 3 entregas

`**89.06** · 0.00 · 0.00`

> ⚠ **Cambió, y afecta a la narración de la demo.** Antes EV-C salía **limpia** (`0.00` los tres):
> DC1 era el documento donante y se analizaba con el almacén de firmas vacío, así que no tenía
> contra qué cruzar. Al recalibrar, EV-A ya tenía firmas, y el cruce funciona **en los dos
> sentidos**: DC1 ve ahora que su texto está también en EV-A.
>
> Conceptualmente es correcto —los dos documentos son casi idénticos y ambos deben señalarse—
> pero rompe el guion, que presenta EV-C como «la cohorte anterior, limpia».
>
> Para recuperar el comportamiento original hay que **purgar el almacén de firmas** y reanalizar
> en orden estricto (EV-C primero, con el almacén vacío). Decidir cuál de los dos escenarios se
> quiere antes de grabar.

## EV-W · assign 11057 · prueba del cotejo web

3 documentos, `0.00 · 0.00 · 0.00` con umbral. Sin umbral daban `1.07 · 1.07 · 0.82`.

## Lo que hay que comprobar tras un despliegue

```
1. Plugin: versión en disco == versión en BD
2. Analyzer: md5sum de los .py == repo (26 ficheros)
3. Analyzers corriendo como appuser (uid 1000), no root
4. Umbrales en local_adminantiplag_perfiles: 0.10 y 0.20
5. Los porcentajes de arriba, evidencia por evidencia
```

El punto 5 es el único que prueba que el sistema *calcula* igual; los cuatro primeros solo
prueban que están los mismos ficheros.

> **Aviso (`hallazgos/H12.md`)**: el umbral con el que se corrió cada análisis **no se guarda**.
> El rótulo y el reporte resuelven el porcentaje contra la configuración *actual* del perfil, así
> que cambiar un umbral reescribe lo que declaran los análisis pasados. Por eso esta línea base
> lleva fecha y umbral explícitos: sin ellos, no es comparable.
