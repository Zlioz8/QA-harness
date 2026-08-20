**L.1 — La dimensión de CVE de dependencias informa 0, y no es un resultado limpio.** Trivy no
encontró manifiesto que analizar porque `composer.json` está gitignored (§3.4). La compuerta
imprime `PASS dependency findings: 0 (max 50)`. **Ese cero no debe leerse como ausencia de
vulnerabilidades**, sino como ausencia de medición. Se corrige solo cuando §3.4 se cierre.

**L.2 — El conteo de calidad estuvo truncado hasta esta ronda.** El exportador de SonarQube pedía
una sola página de 500 incidencias mientras la API declaraba **736**, y el umbral del perfil valía
exactamente 500: la compuerta habría impreso `PASS quality findings: 500 (max 500)` sobre un
proyecto con 736. Se corrigió paginando antes de emitir este informe, así que **la cifra de esta
ronda (736 en bruto, 307 tras deduplicar por regla y ubicación) sí es completa** — pero conviene
saberlo si se compara con cualquier medición anterior.

**L.3 — La cifra de calidad son 307, no 736.** Ambas son ciertas y miden cosas distintas: 736 son
las ocurrencias, 307 los problemas distintos tras deduplicar por regla y ubicación. El veredicto
usa 307, que es lo que hay que corregir; 736 es cuántas veces aparece.

**L.4 — La dimensión de autorización no se ejecutó, y no por falta de guion.** La matriz de 30
reglas y las pruebas de los mecanismos propios de ADI están escritas y versionadas en el perfil.
Falta el insumo: una segunda cuenta de menor privilegio en el entorno de validación. El
laboratorio se niega a sembrarla por diseño — una matriz contra cuentas que el propio laboratorio
fabricó mide su accesorio, no el control de acceso del sistema.
