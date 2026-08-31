# CONTEXTO — <proyecto>

> **Qué es esto.** Lo que una persona sabe de este proyecto y **no está en ningún artefacto**:
> por qué se decidió lo que se decidió, qué se intentó y falló, y qué quedó a medias. Todo lo
> demás —perfil, repos, dimensiones, hallazgos— lo imprime `make brief TARGET=<t>`; no lo copies
> aquí, porque una copia envejece y contradice a su original.
>
> **Cuándo se escribe.** Al CERRAR sesión, en cinco minutos. **Cuándo se lee.** Lo primero al
> abrir la siguiente, junto con `make brief`.
>
> **Límite: 80 líneas.** Si no cabe, es que estás copiando el informe.
>
> Credenciales y URLs que no salen de esta máquina van en `target.env.local`, **nunca aquí**:
> este archivo se versiona.

## Estado en una frase

<p. ej. «R1 medida y entregada; bloqueada la matriz de autorización por la 2.ª cuenta».>

## Decisiones tomadas, con su razón

- <decisión> — <por qué; qué se descartó y por qué>

## Contra qué se está midiendo

- Despliegue: <local / del equipo / los dos, y qué dimensión corrió contra cuál>
- Ramas: <rama auditada por repo, y por qué esa>
- Cuentas: <qué privilegio, de dónde salieron, si la matriz es AUTORITATIVA o no>

## Lo intentado que NO funcionó

<Vale tanto como lo que sí: evita repetirlo. Si el fallo fue del laboratorio, va también a
BITACORA_LABORATORIO.md; aquí queda el rastro para la próxima sesión.>

## Lo que quedó abierto

- [ ] <pendiente concreto, con el comando o la persona que lo desbloquea>

## Lo que NO se midió, y por qué

<La razón ES el hallazgo. Debe coincidir con GUION_NO_APLICA y con RUN.md — si no coinciden,
uno de los tres miente.>
