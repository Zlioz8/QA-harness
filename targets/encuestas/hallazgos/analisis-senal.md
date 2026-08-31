**Ninguna de las 3.402 incidencias de SonarQube es de seguridad.** Las de seguridad ya se
resolvieron aparte (sin inyección, XSS descartado por saneo, secretos triados). Lo que queda es
deuda de **mantenibilidad y accesibilidad**, y conviene leerla por temas, no por regla — y sobre
todo sin dejarse asustar por la palabra «crítico» de Sonar, que mide complejidad, no riesgo.

**Un apunte sobre las dos cifras que verás.** 3.402 son las OCURRENCIAS brutas (cada línea que
Sonar marca). El gate cuenta **1.475**, que son los pares únicos regla+archivo tras `--dedup`: la
misma regla quince veces en el mismo fichero es UN trabajo, no quince. Las dos son reales y miden
cosas distintas; abajo se razona sobre las ocurrencias porque es como se prioriza por tema.

**Reparto:** 2.264 en la SPA (`encuestas`), 1.138 en el backend (`encuestas_backend`). Cuatro
bloques explican casi todo:

1. **Accesibilidad de la SPA — ~560 incidencias, y es la única con obligación EXTERNA.**
   `S9011` (botón sin `type`, 357), `S6853` (label sin control, 96), `S6848` (elemento interactivo
   no nativo, 52), `S1082` (click sin manejador de teclado, 51). Para una plataforma pública del
   SENA la accesibilidad no es cosmética: es requisito legal (WCAG / Resolución 1519). **Es lo
   primero que triaría** — no por riesgo técnico, sino por exposición institucional, y porque buena
   parte se corrige con reglas de lint automáticas.

2. **Complejidad cognitiva — ~430, y es la única con riesgo TÉCNICO real.** `S3776` (funciones
   demasiado complejas, 165 TS + 117 PHP) y `S1142` (métodos con >3 `return`, 149). Estas sí
   importan: una función que Sonar no puede seguir es una que un humano tampoco, y es donde nacen
   los bugs de la próxima ronda. No se despachan en bloque — hay que mirar las 10-15 peores
   funciones y partirlas. El resto puede esperar.

3. **Modernización de sintaxis — ~800, riesgo casi nulo, autofix.** `S7773` (`parseInt` →
   `Number.parseInt`, 260), `S6582` (optional chaining, 259), `S3358` (ternarios anidados, 211),
   `S4624` (templates anidados, 55). Es ruido de estilo: un `eslint --fix` / `rector` se lleva la
   mayoría. No debería consumir tiempo humano de triaje.

4. **Duplicación y TODOs — ~575, termómetro, no defecto.** `S1192` (literal duplicado, 310 —
   marcada «crítica» por Sonar, pero es «extrae una constante», no un riesgo) y `S1135` (comentarios
   `TODO`, 264). Los TODO no son hallazgos: son el propio equipo diciendo qué le falta. Sirven como
   medida de madurez, no como cola de trabajo de QA.

**Lo que NO hay que hacer:** tratar los 662 «críticos» de Sonar como críticos de seguridad. Son
`S1192` (duplicar un literal) y `S3776` (complejidad). La severidad de Sonar es de mantenibilidad;
mezclarla con la de seguridad infla el miedo y entierra lo que sí importa (accesibilidad y las 15
funciones más enrevesadas).

**Recomendación de una línea:** pasar un autofix a los bloques 3 y 4, abrir un frente de
accesibilidad (bloque 1) por la obligación legal, y triar a mano solo las funciones del bloque 2.
De 3.402, el trabajo humano real cabe en unas decenas.
