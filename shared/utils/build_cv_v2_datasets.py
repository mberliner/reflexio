"""
Generador de datasets v2 para el protocolo de N seeds (cv_triage_v2, cv_extraction_v2).

PROVENANCIA: el contenido (textos de CV, job description y etiquetas gold) fue
redactado por Claude (Anthropic), un modelo DISTINTO de los que estan bajo prueba
(task: gpt-4.1-mini/gpt-5-mini; reflection: gpt-5). Esto evita la circularidad de
generar y evaluar con la misma familia de modelos.

DISEÑO:
- Ruido de la vida real inyectado en los INPUTS: acentos faltantes, typos, mayusculas
  inconsistentes, fechas en formatos mixtos, mezcla ES/EN, abreviaturas, lineas basura
  (telefono, LinkedIn, "referencias a pedido"), emails con formato raro, campos ausentes.
- Clases balanceadas en triage (fit_alto / fit_medio / no_fit) en los tres splits.
- Casos limite deliberados (fit_medio que falla UN requisito; no_fit con Python pero de
  data science / otra disciplina) para forzar la rubrica de decision.

GATE DE CALIDAD: cada fila lleva la columna `gold_verificado="no"`. Es un borrador de
gold. Un humano DEBE revisar y poner "si" antes de confiar en estos datos como test.
La columna no la usa el pipeline (no es output de la signature ni required_field).

Uso:
    python -m shared.utils.build_cv_v2_datasets
"""

import csv

from shared.paths import get_dspy_paths, get_gepa_paths

# ---------------------------------------------------------------------------
# TRIAGE: vacante unica (se repite el job_description en todas las filas).
# ---------------------------------------------------------------------------

JD = (
    "Backend Senior (Python) - Equipo distribuido LATAM\n\n"
    "Buscamos backend senior con foco en Python para un equipo distribuido en LATAM.\n\n"
    "Requisitos excluyentes:\n"
    "- 5+ años de experiencia en backend con Python.\n"
    "- Solidez en Django y/o FastAPI.\n"
    "- PostgreSQL y diseño de APIs REST.\n"
    "- Ingles tecnico B2 o superior (equipo internacional, docs en ingles).\n"
    "- Residencia en LATAM (zona horaria GMT-3 a GMT-6).\n\n"
    "Deseable: Docker, AWS, Celery, microservicios.\n"
    "No aplica para perfiles de frontend, mobile, data science ni QA."
)

# (split, cv_text, fit_label, justificacion)
TRIAGE_ROWS = [
    # ===================== fit_alto =====================
    (
        "train",
        "MARTIN GOMEZ\nmartin.gomez@gmail.com | Buenos Aires, Argentina\n\n"
        "Backend Senior. 7 años con Python.\nDjango, FastAPI, PostgreSQL, Docker, AWS.\n"
        "Ingles C1 (trabaje 2 años con equipo en USA).\nReferencias a pedido.",
        "fit_alto",
        "Python senior en LATAM, Django/FastAPI+PostgreSQL e ingles C1: cumple todo.",
    ),
    (
        "train",
        "Lucia Fernandez\nSenior Software Engineer (Backend)\n"
        "CDMX, Mexico - lucia.fernandez@outlook.com\n"
        "6 anios desarrollando APIs REST con FastAPI y Django.\nPostgreSQL, Celery, Docker.\n"
        "Ingles B2 certificado (EF SET).",
        "fit_alto",
        "6 años Python, FastAPI/Django, PostgreSQL, ingles B2, residente en Mexico (LATAM).",
    ),
    (
        "train",
        "CARLOS RUIZ\nbogota, colombia\ncarlosruiz dev @ proton.me\n\n"
        "8 years backend python. django rest framework, postgres, microservicios.\n"
        "advanced english. aws (eks, lambda).",
        "fit_alto",
        "8 años Python/Django, PostgreSQL, microservicios, ingles avanzado, en Colombia.",
    ),
    (
        "train",
        "Ana Paula Souza\nMontevideo, Uruguay\nap.souza@empresa.com.uy\n"
        "Ingeniera de Software | 9 anos | Python\nDjango, FastAPI, PostgreSQL, AWS, Celery\n"
        "Ingles fluido (vivi 3 anos en Canada)",
        "fit_alto",
        "9 años Python, stack completo, ingles fluido, Uruguay: cumple todos los requisitos.",
    ),
    (
        "val",
        "Diego Torres - diego.torres@mail.com\nSantiago de Chile\n"
        "5 años Python backend. FastAPI + PostgreSQL. Docker.\nIngles B2.",
        "fit_alto",
        "5 años Python, FastAPI+PostgreSQL, ingles B2, Chile: cumple el minimo de todo.",
    ),
    (
        "val",
        "RODRIGO MENDES\nLima, Peru\nrodrigo_mendes@gmail.com\n"
        "Backend dev senior, 6 yrs. Django y FastAPI. Postgres. REST APIs.\n"
        "English B2.",
        "fit_alto",
        "6 años Python con Django/FastAPI, PostgreSQL, ingles B2, residente en Peru.",
    ),
    (
        "test",
        "Sofia Ramirez\nremoto desde Cordoba, Argentina\nsofia.ramirez88@gmail.com\n"
        "7 anios Python. Django REST, PostgreSQL, Celery, Docker.\nIngles C1.",
        "fit_alto",
        "7 años Python/Django, PostgreSQL, ingles C1, Argentina (LATAM): cumple todo.",
    ),
    (
        "test",
        "GABRIEL SILVA\nFlorianopolis, Brasil | gabriel.silva@dev.br\n"
        "Senior Backend Engineer - 8 anos - Python\nFastAPI, Django, PostgreSQL, AWS, Docker\n"
        "Ingles avanzado (B2/C1).",
        "fit_alto",
        "8 años Python, FastAPI/Django+PostgreSQL, ingles avanzado, Brasil (LATAM).",
    ),
    (
        "test",
        "valentina lopez\nquito, ecuador\nvalentina.lopez@correo.ec\n"
        "6 anos backend python, django, fastapi, postgresql, redis, docker\n"
        "ingles b2",
        "fit_alto",
        "6 años Python con Django/FastAPI, PostgreSQL, ingles B2, Ecuador: cumple.",
    ),
    # ===================== fit_medio =====================
    (
        "train",
        "PEDRO ALVAREZ\nBuenos Aires, Argentina\npedro.alvarez@gmail.com\n"
        "6 años Python. Django, PostgreSQL, Docker.\nIngles basico (A2), en mejora.",
        "fit_medio",
        "Cumple nucleo tecnico (Python senior, Django, PG, LATAM) pero ingles A2 < B2.",
    ),
    (
        "train",
        "Marta Gil\nMadrid, España - marta.gil@empresa.es\n"
        "Backend Python, 7 anios. Django, FastAPI, PostgreSQL. Ingles C1.",
        "fit_medio",
        "Stack e ingles perfectos pero reside en España, fuera de LATAM (GMT+1).",
    ),
    (
        "train",
        "JUAN DAVID MORENO\nMedellin, Colombia\njuandavid@mail.com\n"
        "3 años de experiencia. Python con FastAPI. PostgreSQL. Ingles B2.",
        "fit_medio",
        "Cumple stack/idioma/ubicacion pero 3 años no alcanza el seniority de 5+.",
    ),
    (
        "val",
        "Bruno Costa - bruno.costa@webmail.com\nSao Paulo, Brasil\n"
        "Senior backend, 7 anos. Stack: Flask, PostgreSQL, Docker. Ingles B2.",
        "fit_medio",
        "Senior Python en LATAM con ingles B2 pero usa Flask (stack adyacente, no Django/FastAPI).",
    ),
    (
        "val",
        "CAMILA HERRERA\nLima, Peru | camila.herrera@gmail.com\n"
        "Python backend 6 años. Django, PostgreSQL.\n(no se menciona nivel de ingles)",
        "fit_medio",
        "Nucleo tecnico y ubicacion OK pero no acredita ingles B2 (requisito excluyente).",
    ),
    (
        "test",
        "Nicolas Pereyra\nMontevideo, Uruguay\nnico.pereyra@mail.uy\n"
        "4 anios Python. Django REST, PostgreSQL, Docker. Ingles C1.",
        "fit_medio",
        "Stack, idioma y ubicacion OK pero 4 años queda por debajo del minimo de 5+.",
    ),
    (
        "test",
        "ANDREA NUNEZ\nbarcelona, españa\nandrea.nunez@correo.es\n"
        "Python senior 8 anos. FastAPI, Django, PostgreSQL. English C1.",
        "fit_medio",
        "Perfil tecnico ideal pero residencia en España (fuera de LATAM).",
    ),
    (
        "test",
        "Felipe Vargas\nValparaiso, Chile - felipe.vargas@gmail.com\n"
        "6 años Python. Django, PostgreSQL. Ingles A2 (lectura tecnica solamente).",
        "fit_medio",
        "Senior Python/Django/PG en LATAM pero ingles A2, debajo del B2 requerido.",
    ),
    # ===================== no_fit =====================
    (
        "train",
        "ESTEBAN DIAZ\nBuenos Aires, Argentina\nesteban.diaz@gmail.com\n"
        "Backend Java/Spring Boot, 8 años. PostgreSQL, microservicios. Ingles C1.",
        "no_fit",
        "Perfil backend solido pero en Java/Spring, no Python: lenguaje desalineado.",
    ),
    (
        "train",
        "Paula Castro - paula.castro@mail.com\nCDMX, Mexico\n"
        "Frontend Developer. 6 anios. React, Angular, TypeScript, CSS. Ingles B2.",
        "no_fit",
        "Disciplina frontend, no backend Python; el aviso excluye frontend.",
    ),
    (
        "train",
        "RICARDO GOMEZ\nbogota\nricardo.gomez@webmail.com\n"
        "7 años PHP / Laravel. MySQL. APIs REST. Ingles B1.",
        "no_fit",
        "Backend pero en PHP/Laravel, no Python: lenguaje desalineado.",
    ),
    (
        "val",
        "Mariana Lopez\nSantiago, Chile\nmariana.lopez@datos.cl\n"
        "Data Scientist. 5 anos Python (pandas, scikit-learn, TensorFlow). SQL. Ingles C1.",
        "no_fit",
        "Usa Python pero en data science (excluido en el aviso); no es backend web.",
    ),
    (
        "val",
        "JORGE RAMOS - jorge.ramos@mail.com\nLima, Peru\n"
        "Desarrollador .NET / C#, 9 años. SQL Server. Azure. Ingles B2.",
        "no_fit",
        "Backend en .NET/C#, no Python: lenguaje desalineado.",
    ),
    (
        "test",
        "Tomas Aguirre\nBuenos Aires\ntomas.aguirre@gmail.com\n"
        "QA Automation Engineer, 6 anios. Selenium, algo de Python para scripts. Ingles B2.",
        "no_fit",
        "Perfil QA (excluido) y Python solo para scripting, no desarrollo backend.",
    ),
    (
        "test",
        "LAURA MENDEZ\nmexico city\nlaura.mendez@correo.mx\n"
        "DevOps / SRE, 7 anos. Terraform, Kubernetes, Bash, Go. Ingles C1.",
        "no_fit",
        "Disciplina DevOps/SRE, no desarrollo backend con Python.",
    ),
    (
        "test",
        "Sebastian Rios - sebastian.rios@mail.com\nMadrid, España\n"
        "Mobile dev (Android/Kotlin), 5 años. Ingles A2.",
        "no_fit",
        "Disciplina mobile (excluida), fuera de LATAM e ingles A2: multiples fallos criticos.",
    ),
    (
        "test",
        "CAROLINA FUENTES\nbogota, colombia\ncarolina.fuentes@gmail.com\n"
        "Backend Ruby on Rails, 6 anios. PostgreSQL, REST. Ingles B2.",
        "no_fit",
        "Backend solido pero en Ruby on Rails, no Python: lenguaje desalineado.",
    ),
    (
        "test",
        "Hernan Vega\nrosario, argentina\nhernan.vega@webmail.com\n"
        "Analista funcional / PM tecnico, 10 anos. SQL, Excel, Jira. Ingles B1.",
        "no_fit",
        "Rol funcional/PM, no desarrollo backend Python: disciplina desalineada.",
    ),
    # --- test extra para balancear 7/7/7 ---
    (
        "test",
        "Mariano Castro\nAsuncion, Paraguay\nmariano.castro@mail.com.py\n"
        "6 anios Python backend. Django, FastAPI, PostgreSQL. Ingles B2.",
        "fit_alto",
        "6 años Python con Django/FastAPI, PostgreSQL, ingles B2, Paraguay (LATAM).",
    ),
    (
        "test",
        "DANIELA ORTIZ\nLa Paz, Bolivia | daniela.ortiz@correo.bo\n"
        "7 years senior backend. FastAPI, PostgreSQL, Docker, Celery. English C1.",
        "fit_alto",
        "7 años Python/FastAPI, PostgreSQL, ingles C1, Bolivia: cumple todo.",
    ),
    (
        "test",
        "ignacio funes\nremoto desde mendoza, argentina\nignacio.funes@gmail.com\n"
        "5 anos python. django rest framework, postgresql, aws. ingles b2.",
        "fit_alto",
        "5 años Python/Django, PostgreSQL, AWS, ingles B2, Argentina: cumple el minimo.",
    ),
    (
        "test",
        "Renata Lima - renata.lima@dev.br\nRecife, Brasil\n"
        "9 anos Python. Django, PostgreSQL, microservicios, Docker. Ingles avanzado.",
        "fit_alto",
        "9 años Python/Django, PostgreSQL, microservicios, ingles avanzado, Brasil.",
    ),
    (
        "test",
        "Oscar Mendez\nciudad de guatemala, guatemala\noscar.mendez@mail.gt\n"
        "4 años Python. Django, PostgreSQL, Docker. Ingles B2.",
        "fit_medio",
        "Stack, idioma y ubicacion OK pero 4 años no alcanza el seniority de 5+.",
    ),
    (
        "test",
        "PATRICIA ROJAS\nSan Jose, Costa Rica\npatricia.rojas@correo.cr\n"
        "6 anios Python senior. Django, PostgreSQL. Ingles A2.",
        "fit_medio",
        "Senior Python/Django/PG en LATAM pero ingles A2, debajo del B2 requerido.",
    ),
    (
        "test",
        "Joao Almeida\nLisboa, Portugal - joao.almeida@mail.pt\n"
        "7 anos Python. FastAPI, PostgreSQL. Ingles C1.",
        "fit_medio",
        "Perfil tecnico ideal pero reside en Portugal, fuera de LATAM.",
    ),
    (
        "test",
        "MONICA SALAS\nLima, Peru\nmonica.salas@gmail.com\n"
        "8 años Python senior. Flask + SQLAlchemy, PostgreSQL, Docker. Ingles B2.",
        "fit_medio",
        "Senior Python en LATAM con ingles B2 pero usa Flask (stack adyacente, no Django/FastAPI).",
    ),
    (
        "test",
        "Bruno Tavares\nbogota, colombia\nbruno.tavares@webmail.com\n"
        "7 anios backend en Go (Golang). gRPC, PostgreSQL, Kubernetes. Ingles C1.",
        "no_fit",
        "Backend solido pero en Go, no Python: lenguaje desalineado.",
    ),
    (
        "test",
        "Veronica Luna - veronica.luna@mail.com\nSantiago, Chile\n"
        "6 años como desarrolladora Salesforce / low-code. Apex, flujos. Ingles B2.",
        "no_fit",
        "Disciplina Salesforce/low-code, no backend Python: perfil desalineado.",
    ),
    # --- val extra para balancear 4/4/4 ---
    (
        "val",
        "Emilia Rojas\nTegucigalpa, Honduras | emilia.rojas@correo.hn\n"
        "6 anios Python backend. Django, FastAPI, PostgreSQL, Docker. Ingles B2.",
        "fit_alto",
        "6 años Python con Django/FastAPI, PostgreSQL, ingles B2, Honduras (LATAM).",
    ),
    (
        "val",
        "JAVIER MOLINA\nCaracas, Venezuela\njavier.molina@mail.com.ve\n"
        "8 years senior Python. Django, PostgreSQL, microservicios. English C1.",
        "fit_alto",
        "8 años Python/Django, PostgreSQL, microservicios, ingles C1, Venezuela (LATAM).",
    ),
    (
        "val",
        "Lucas Benitez\nCiudad de Panama, Panama\nlucas.benitez@correo.pa\n"
        "4 años Python. Django, PostgreSQL, Docker. Ingles B2.",
        "fit_medio",
        "Stack, idioma y ubicacion OK pero 4 años no alcanza el seniority de 5+.",
    ),
    (
        "val",
        "ROMINA CACERES\nRosario, Argentina - romina.caceres@gmail.com\n"
        "7 anios Python senior. FastAPI, PostgreSQL, Celery. Ingles A2.",
        "fit_medio",
        "Senior Python/FastAPI/PG en LATAM pero ingles A2, debajo del B2 requerido.",
    ),
    (
        "val",
        "Damian Ferreyra\nLima, Peru\ndamian.ferreyra@webmail.com\n"
        "5 años como desarrollador frontend. Vue, React, JavaScript, CSS. Ingles B2.",
        "no_fit",
        "Disciplina frontend, no backend Python; el aviso excluye frontend.",
    ),
    (
        "val",
        "NORA SANTILLAN\nbogota, colombia\nnora.santillan@correo.co\n"
        "9 anios en sistemas embebidos. C, C++, microcontroladores, RTOS. Ingles C1.",
        "no_fit",
        "Disciplina embebidos en C/C++, no backend Python: perfil desalineado.",
    ),
]

# ---------------------------------------------------------------------------
# EXTRACTION: 5 campos. Ruido en el texto; gold = forma canonica correcta.
# Campos: nombre, email, años_experiencia (int), skills (coma), educacion_principal.
# ---------------------------------------------------------------------------

# (split, text, nombre, email, años_experiencia, skills, educacion_principal)
EXTRACTION_ROWS = [
    (
        "train",
        "Dr. Roberto Salinas\nroberto.salinas@uni.edu\n"
        "EXPERIENCIA: 12 años en investigacion y desarrollo de software.\n"
        "Competente en Python, C++ y CUDA.\n"
        "Doctorado en Ciencias de la Computacion, MIT.",
        "Roberto Salinas",
        "roberto.salinas@uni.edu",
        "12",
        "Python, C++, CUDA",
        "Doctorado Ciencias Computacion, MIT",
    ),
    (
        "train",
        "MARIA JOSE RIVERO\nContacto: mjrivero (arroba) gmail.com\n"
        "8+ años de experiencia como Product Manager.\n"
        "Habilidades: Roadmap, Scrum, Jira, Analisis de Datos.\n"
        "Licenciatura en Administracion, UBA.",
        "Maria Jose Rivero",
        "mjrivero@gmail.com",
        "8",
        "Roadmap, Scrum, Jira, Analisis de Datos",
        "Licenciatura Administracion, UBA",
    ),
    (
        "train",
        "ing. Pablo Nunez\np.nunez@empresa.com.ar\n"
        "Desarrollador desde 2017.\nTecnologias: Java, Spring, MySQL, Docker.\n"
        "Ingenieria en Sistemas, UTN.",
        "Pablo Nunez",
        "p.nunez@empresa.com.ar",
        "8",
        "Java, Spring, MySQL, Docker",
        "Ingenieria Sistemas, UTN",
    ),
    (
        "train",
        "Lucia Ferraro\nlucia.ferraro@mail.com\n"
        "Disenadora UX/UI con 5 anios de experiencia.\n"
        "Figma, Sketch, Investigacion de usuarios, Prototipado.\n"
        "Grado en Diseno Grafico, RISD.",
        "Lucia Ferraro",
        "lucia.ferraro@mail.com",
        "5",
        "Figma, Sketch, Investigacion de usuarios, Prototipado",
        "Grado Diseno Grafico, RISD",
    ),
    (
        "train",
        "JUAN PEREZ\njuan.perez@email.com\nEXPERIENCIA: 5 anos en desarrollo de software\n"
        "HABILIDADES: Python, Machine Learning, Docker\n"
        "Maestria en Ciencia de Datos, Universidad de Stanford",
        "Juan Perez",
        "juan.perez@email.com",
        "5",
        "Python, Machine Learning, Docker",
        "Maestria Ciencia Datos, Stanford",
    ),
    (
        "train",
        "Sandra Gil | sandra.gil@corp.io | +54 11 5555-1234\n"
        "Mas de 10 años en marketing digital.\n"
        "Competente en SEO, SEM, Google Analytics y Content Strategy.\n"
        "Lic. en Comunicacion, Universidad Austral.",
        "Sandra Gil",
        "sandra.gil@corp.io",
        "10",
        "SEO, SEM, Google Analytics, Content Strategy",
        "Licenciatura Comunicacion, Universidad Austral",
    ),
    (
        "val",
        "Lic. Andrea Bianchi\nandrea.bianchi@consultora.com\n"
        "Experiencia: 7 años en finanzas corporativas.\n"
        "Modelado Financiero, Excel avanzado, Valuacion, SQL.\n"
        "MBA, IAE Business School.",
        "Andrea Bianchi",
        "andrea.bianchi@consultora.com",
        "7",
        "Modelado Financiero, Excel, Valuacion, SQL",
        "MBA, IAE Business School",
    ),
    (
        "val",
        "FERNANDO CASTRO\nfernando.castro@dev.io\n"
        "Trabajo en backend desde 2015 a la fecha.\n"
        "Skills: Python, Django, PostgreSQL, AWS.\n"
        "Ingenieria Informatica, Universidad de Chile.",
        "Fernando Castro",
        "fernando.castro@dev.io",
        "9",
        "Python, Django, PostgreSQL, AWS",
        "Ingenieria Informatica, Universidad Chile",
    ),
    (
        "val",
        "natalia romero\nnatalia.romero @ outlook.com\n"
        "3 años como analista de datos.\n"
        "python, sql, power bi, tableau, estadistica\n"
        "licenciatura en estadistica, universidad nacional de cordoba",
        "Natalia Romero",
        "natalia.romero@outlook.com",
        "3",
        "Python, SQL, Power BI, Tableau, Estadistica",
        "Licenciatura Estadistica, Universidad Nacional Cordoba",
    ),
    (
        "val",
        "DIEGO MORALES\nemail: diego.morales@empresa.mx\n"
        "(aprox. 6 años de experiencia)\n"
        "Tecnologias: React, Node.js, MongoDB, TypeScript\n"
        "Ing. en Tecnologias de la Informacion, Tec de Monterrey",
        "Diego Morales",
        "diego.morales@empresa.mx",
        "6",
        "React, Node.js, MongoDB, TypeScript",
        "Ingenieria Tecnologias Informacion, Tec de Monterrey",
    ),
    (
        "test",
        "Dra. Carmen Ortiz\ncarmen.ortiz@hospital.org\n"
        "15 años de trayectoria en investigacion biomedica.\n"
        "Competente en bioestadistica, R, Python y redaccion cientifica.\n"
        "Doctorado en Medicina, Universidad de Buenos Aires.",
        "Carmen Ortiz",
        "carmen.ortiz@hospital.org",
        "15",
        "Bioestadistica, R, Python, Redaccion Cientifica",
        "Doctorado Medicina, Universidad Buenos Aires",
    ),
    (
        "test",
        "GASTON ROMERO\ngaston.romero@gmail.com\n"
        "Experiencia 2012-2020 como desarrollador web.\n"
        "PHP, Laravel, MySQL, JavaScript, Vue.\n"
        "Tecnicatura en Programacion, UTN.",
        "Gaston Romero",
        "gaston.romero@gmail.com",
        "8",
        "PHP, Laravel, MySQL, JavaScript, Vue",
        "Tecnicatura Programacion, UTN",
    ),
    (
        "test",
        "valeria sosa\nvaleria.sosa@correo.com.uy\n"
        "7+ anios liderando equipos de ventas.\n"
        "Negociacion de Contratos, Generacion de Leads, CRM, Salesforce.\n"
        "Licenciatura en Marketing, Universidad ORT.",
        "Valeria Sosa",
        "valeria.sosa@correo.com.uy",
        "7",
        "Negociacion de Contratos, Generacion de Leads, CRM, Salesforce",
        "Licenciatura Marketing, Universidad ORT",
    ),
    (
        "test",
        "Sr. Tomas Iglesias\ntomas.iglesias@startup.io\n"
        "Cinco anos de experiencia en DevOps.\n"
        "Docker, Kubernetes, Terraform, AWS, Bash.\n"
        "Ingenieria en Sistemas, Universidad Tecnologica Nacional.",
        "Tomas Iglesias",
        "tomas.iglesias@startup.io",
        "5",
        "Docker, Kubernetes, Terraform, AWS, Bash",
        "Ingenieria Sistemas, Universidad Tecnologica Nacional",
    ),
    (
        "test",
        "PAULA MENDEZ\npaula.mendez@mail.com\n"
        "Desde 2019 trabajando en QA.\n"
        "Selenium, Python, Postman, JIRA, pruebas automatizadas.\n"
        "Tecnicatura en Testing de Software, UNLP.",
        "Paula Mendez",
        "paula.mendez@mail.com",
        "6",
        "Selenium, Python, Postman, JIRA, Pruebas Automatizadas",
        "Tecnicatura Testing Software, UNLP",
    ),
    (
        "test",
        "ricardo blanco\nricardo.blanco@empresa.cl\n"
        "mas de 9 años en arquitectura de software\n"
        "java, kotlin, spring, kafka, microservicios\n"
        "magister en ingenieria de software, pontificia universidad catolica",
        "Ricardo Blanco",
        "ricardo.blanco@empresa.cl",
        "9",
        "Java, Kotlin, Spring, Kafka, Microservicios",
        "Magister Ingenieria Software, Pontificia Universidad Catolica",
    ),
    (
        "test",
        "Ing. Florencia Diaz\nflorencia.diaz@consultora.com.ar\n"
        "4 años de experiencia en ciencia de datos.\n"
        "Competente en Python, pandas, scikit-learn, SQL y visualizacion.\n"
        "Licenciatura en Matematica, Universidad de Buenos Aires.",
        "Florencia Diaz",
        "florencia.diaz@consultora.com.ar",
        "4",
        "Python, pandas, scikit-learn, SQL, Visualizacion",
        "Licenciatura Matematica, Universidad Buenos Aires",
    ),
    (
        "test",
        "MARCOS LEON\nmarcos.leon@webmail.com | LinkedIn: /in/marcosleon\n"
        "Experiencia profesional: 11 anios en desarrollo backend.\n"
        "Python, FastAPI, PostgreSQL, Redis, Docker, CI/CD.\n"
        "Ingenieria en Computacion, Universidad Nacional de La Plata.",
        "Marcos Leon",
        "marcos.leon@webmail.com",
        "11",
        "Python, FastAPI, PostgreSQL, Redis, Docker, CI/CD",
        "Ingenieria Computacion, Universidad Nacional La Plata",
    ),
    (
        "test",
        "lorena vega\nlorena.vega@correo.pe\n"
        "8 anos en gestion de proyectos.\n"
        "PMP, Scrum, Kanban, MS Project, liderazgo de equipos.\n"
        "MBA, Universidad del Pacifico.",
        "Lorena Vega",
        "lorena.vega@correo.pe",
        "8",
        "PMP, Scrum, Kanban, MS Project, Liderazgo",
        "MBA, Universidad Pacifico",
    ),
    (
        "test",
        "Sebastian Rey - sebastian.rey@gmail.com\n"
        "(7 anos) Ingeniero de datos.\n"
        "Spark, Python, Airflow, SQL, Snowflake, dbt.\n"
        "Ingenieria Industrial, ITBA.",
        "Sebastian Rey",
        "sebastian.rey@gmail.com",
        "7",
        "Spark, Python, Airflow, SQL, Snowflake, dbt",
        "Ingenieria Industrial, ITBA",
    ),
    (
        "test",
        "CECILIA PAZ\ncecilia.paz@empresa.com\n"
        "Mas de 6 años en recursos humanos.\n"
        "Reclutamiento, Onboarding, Workday, Comunicacion Interna.\n"
        "Licenciatura en Psicologia, Universidad de Palermo.",
        "Cecilia Paz",
        "cecilia.paz@empresa.com",
        "6",
        "Reclutamiento, Onboarding, Workday, Comunicacion Interna",
        "Licenciatura Psicologia, Universidad Palermo",
    ),
    (
        "test",
        "martin aceves\nmartin.aceves@correo.mx\ndesde 2014 en desarrollo movil\n"
        "Swift, Objective-C, Kotlin, Firebase\n"
        "Ingenieria en Software, Universidad de Guadalajara",
        "Martin Aceves",
        "martin.aceves@correo.mx",
        "12",
        "Swift, Objective-C, Kotlin, Firebase",
        "Ingenieria Software, Universidad Guadalajara",
    ),
    (
        "test",
        "Dr. Alejandro Vidal\nalejandro.vidal@lab.edu\n"
        "20 años de experiencia academica e industrial.\n"
        "Competente en C, C++, Rust, sistemas embebidos y RTOS.\n"
        "PhD en Ingenieria Electronica, Caltech.",
        "Alejandro Vidal",
        "alejandro.vidal@lab.edu",
        "20",
        "C, C++, Rust, Sistemas Embebidos, RTOS",
        "PhD Ingenieria Electronica, Caltech",
    ),
    # --- test extra para llegar a >=20 ---
    (
        "test",
        "Lic. Mateo Fuentes\nmateo.fuentes@empresa.com.ar\n"
        "Experiencia: 9 anos en desarrollo full stack.\n"
        "Angular, TypeScript, Node.js, Express, MongoDB, Docker.\n"
        "Licenciatura en Sistemas de Informacion, Universidad de Belgrano.",
        "Mateo Fuentes",
        "mateo.fuentes@empresa.com.ar",
        "9",
        "Angular, TypeScript, Node.js, Express, MongoDB, Docker",
        "Licenciatura Sistemas Informacion, Universidad Belgrano",
    ),
    (
        "test",
        "JULIETA NAVARRO\njulieta.navarro@correo.com\n"
        "Mas de 4 años en disenio grafico y branding.\n"
        "Adobe Illustrator, Photoshop, InDesign, Branding, Tipografia.\n"
        "Grado en Disenio, Universidad de Palermo.",
        "Julieta Navarro",
        "julieta.navarro@correo.com",
        "4",
        "Adobe Illustrator, Photoshop, InDesign, Branding, Tipografia",
        "Grado Disenio, Universidad Palermo",
    ),
    (
        "test",
        "ramiro guzman\nramiro.guzman @ gmail.com\n"
        "13 anos en bases de datos y administracion de sistemas.\n"
        "Oracle, PostgreSQL, MySQL, Linux, Bash, Ansible.\n"
        "Ingenieria en Informatica, Universidad Tecnologica Nacional.",
        "Ramiro Guzman",
        "ramiro.guzman@gmail.com",
        "13",
        "Oracle, PostgreSQL, MySQL, Linux, Bash, Ansible",
        "Ingenieria Informatica, Universidad Tecnologica Nacional",
    ),
    (
        "test",
        "Sra. Beatriz Campos\nbeatriz.campos@consultora.cl\n"
        "Experiencia 2006-2021 en auditoria y finanzas.\n"
        "Auditoria, IFRS, SAP, Excel avanzado, Control de Gestion.\n"
        "Contadora Publica, Universidad de Chile.",
        "Beatriz Campos",
        "beatriz.campos@consultora.cl",
        "15",
        "Auditoria, IFRS, SAP, Excel, Control de Gestion",
        "Contadora Publica, Universidad Chile",
    ),
    (
        "test",
        "EMILIANO PRADO\nemiliano.prado@startup.io | tel 351-555-9090\n"
        "8+ anios en machine learning e inteligencia artificial.\n"
        "Python, PyTorch, TensorFlow, MLOps, Kubernetes.\n"
        "Maestria en Inteligencia Artificial, Universidad Politecnica de Madrid.",
        "Emiliano Prado",
        "emiliano.prado@startup.io",
        "8",
        "Python, PyTorch, TensorFlow, MLOps, Kubernetes",
        "Maestria Inteligencia Artificial, Universidad Politecnica Madrid",
    ),
    (
        "test",
        "carla espinoza\ncarla.espinoza@correo.pe\n"
        "desde 2018 en desarrollo backend\n"
        "python, fastapi, postgresql, redis, rabbitmq\n"
        "ingenieria de sistemas, universidad nacional de ingenieria",
        "Carla Espinoza",
        "carla.espinoza@correo.pe",
        "8",
        "Python, FastAPI, PostgreSQL, Redis, RabbitMQ",
        "Ingenieria Sistemas, Universidad Nacional Ingenieria",
    ),
    (
        "test",
        "Ing. Gonzalo Ledesma\ngonzalo.ledesma@empresa.com.mx\n"
        "Aproximadamente 6 años en ciberseguridad.\n"
        "Pentesting, SIEM, Python, Redes, Análisis de Malware.\n"
        "Maestria en Seguridad Informatica, ITESM.",
        "Gonzalo Ledesma",
        "gonzalo.ledesma@empresa.com.mx",
        "6",
        "Pentesting, SIEM, Python, Redes, Analisis de Malware",
        "Maestria Seguridad Informatica, ITESM",
    ),
    # --- val extra para ampliar la senal de optimizacion (4 -> 10) ---
    (
        "val",
        "Prof. Adriana Molina\nadriana.molina@colegio.edu.ar\n"
        "Experiencia: 14 años en docencia secundaria y universitaria.\n"
        "Didactica, Evaluacion, Moodle, Planificacion, Oratoria.\n"
        "Profesorado en Matematica, Universidad Nacional de Cuyo.",
        "Adriana Molina",
        "adriana.molina@colegio.edu.ar",
        "14",
        "Didactica, Evaluacion, Moodle, Planificacion, Oratoria",
        "Profesorado Matematica, Universidad Nacional Cuyo",
    ),
    (
        "val",
        "BRUNO IGLESIAS\nbruno.iglesias@dev.com\n"
        "Trabajando en backend desde 2016.\n"
        "Python, Django, FastAPI, PostgreSQL, Redis, Docker.\n"
        "Ingenieria en Sistemas, Universidad Tecnologica Nacional.",
        "Bruno Iglesias",
        "bruno.iglesias@dev.com",
        "9",
        "Python, Django, FastAPI, PostgreSQL, Redis, Docker",
        "Ingenieria Sistemas, Universidad Tecnologica Nacional",
    ),
    (
        "val",
        "Cra. Veronica Sosa\nveronica.sosa@estudio.com.ar | 011-4444-2020\n"
        "Mas de 11 años en contabilidad y tributacion.\n"
        "Impuestos, Balances, SAP, Excel, Conciliaciones.\n"
        "Contadora Publica, Universidad de Buenos Aires.",
        "Veronica Sosa",
        "veronica.sosa@estudio.com.ar",
        "11",
        "Impuestos, Balances, SAP, Excel, Conciliaciones",
        "Contadora Publica, Universidad Buenos Aires",
    ),
    (
        "val",
        "ing. matias paredes\nmatias.paredes @ constructora.cl\n"
        "experiencia 2009-2023 en ingenieria civil\n"
        "autocad, revit, gestion de obra, presupuestos, ms project\n"
        "ingenieria civil, pontificia universidad catolica de chile",
        "Matias Paredes",
        "matias.paredes@constructora.cl",
        "14",
        "AutoCAD, Revit, Gestion de Obra, Presupuestos, MS Project",
        "Ingenieria Civil, Pontificia Universidad Catolica Chile",
    ),
    (
        "val",
        "Daniela Cruz - daniela.cruz@traducciones.com\n"
        "(aprox. 8 años) Traductora e interprete.\n"
        "Ingles, Portugues, Frances, Trados, Subtitulado.\n"
        "Licenciatura en Traductorado, Universidad del Salvador.",
        "Daniela Cruz",
        "daniela.cruz@traducciones.com",
        "8",
        "Ingles, Portugues, Frances, Trados, Subtitulado",
        "Licenciatura Traductorado, Universidad Salvador",
    ),
    (
        "val",
        "Dr. Federico Lara\nfederico.lara@investigacion.org\n"
        "18 años en investigacion en fisica de particulas.\n"
        "Competente en Python, ROOT, C++, analisis de datos y LaTeX.\n"
        "Doctorado en Fisica, Instituto Balseiro.",
        "Federico Lara",
        "federico.lara@investigacion.org",
        "18",
        "Python, ROOT, C++, Analisis de Datos, LaTeX",
        "Doctorado Fisica, Instituto Balseiro",
    ),
]


def _write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"Escrito: {path} ({len(rows)} filas)")


def main() -> int:
    dspy_ds = get_dspy_paths().datasets
    gepa_ds = get_gepa_paths().datasets

    triage_header = [
        "split",
        "cv_text",
        "job_description",
        "fit_label",
        "justificacion",
        "gold_verificado",
    ]
    triage_rows = [[split, cv, JD, label, just, "no"] for (split, cv, label, just) in TRIAGE_ROWS]
    _write_csv(dspy_ds / "cv_triage_v2.csv", triage_header, triage_rows)

    extraction_header = [
        "split",
        "text",
        "nombre",
        "email",
        "años_experiencia",
        "skills",
        "educacion_principal",
        "gold_verificado",
    ]
    extraction_rows = [
        [split, text, nombre, email, anios, skills, edu, "no"]
        for (split, text, nombre, email, anios, skills, edu) in EXTRACTION_ROWS
    ]
    _write_csv(gepa_ds / "cv_extraction_v2.csv", extraction_header, extraction_rows)

    # Resumen de balance de clases para triage.
    from collections import Counter

    for split in ("train", "val", "test"):
        c = Counter(label for (s, _, label, _) in TRIAGE_ROWS if s == split)
        print(f"  triage {split}: {dict(c)}")
    for split in ("train", "val", "test"):
        n = sum(1 for r in EXTRACTION_ROWS if r[0] == split)
        print(f"  extraction {split}: {n} filas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
