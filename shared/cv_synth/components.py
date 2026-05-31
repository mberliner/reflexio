"""Pools de componentes para componer CVs realistas y variados.

Modular: agregar una ciudad, universidad, frase o sector es tocar una sola lista
aqui. render.py elige de estos pools con un ``random.Random`` sembrado por
candidato, asi la salida es reproducible byte a byte.
"""

from __future__ import annotations

# (ciudad, pais, gmt, region). region "LATAM" habilita el requisito de ubicacion.
CITIES: list[tuple[str, str, int, str]] = [
    ("Buenos Aires", "Argentina", -3, "LATAM"),
    ("Cordoba", "Argentina", -3, "LATAM"),
    ("Rosario", "Argentina", -3, "LATAM"),
    ("Montevideo", "Uruguay", -3, "LATAM"),
    ("Santiago", "Chile", -3, "LATAM"),
    ("Sao Paulo", "Brasil", -3, "LATAM"),
    ("Florianopolis", "Brasil", -3, "LATAM"),
    ("Recife", "Brasil", -3, "LATAM"),
    ("Bogota", "Colombia", -5, "LATAM"),
    ("Medellin", "Colombia", -5, "LATAM"),
    ("Lima", "Peru", -5, "LATAM"),
    ("Quito", "Ecuador", -5, "LATAM"),
    ("Ciudad de Mexico", "Mexico", -6, "LATAM"),
    ("Guadalajara", "Mexico", -6, "LATAM"),
    ("Asuncion", "Paraguay", -3, "LATAM"),
    ("La Paz", "Bolivia", -4, "LATAM"),
    ("San Jose", "Costa Rica", -6, "LATAM"),
    ("Caracas", "Venezuela", -4, "LATAM"),
    # Fuera de LATAM (para no_fit / fit_medio por ubicacion)
    ("Madrid", "España", 1, "Europa"),
    ("Barcelona", "España", 1, "Europa"),
    ("Lisboa", "Portugal", 0, "Europa"),
    ("Miami", "USA", -5, "USA"),
    ("Houston", "USA", -6, "USA"),
    ("Berlin", "Alemania", 1, "Europa"),
]

UNIVERSITIES: list[str] = [
    "Universidad de Buenos Aires",
    "Universidad Tecnologica Nacional",
    "Universidad Nacional de Cordoba",
    "Universidad de la Republica",
    "Universidad de Chile",
    "Pontificia Universidad Catolica de Chile",
    "Universidade de Sao Paulo",
    "Universidad Nacional de Colombia",
    "Universidad de los Andes",
    "Universidad Nacional de Ingenieria",
    "Universidad Nacional Autonoma de Mexico",
    "Instituto Tecnologico de Monterrey",
]

DEGREES: list[str] = [
    "Licenciatura en Ciencias de la Computacion",
    "Ingenieria en Sistemas de Informacion",
    "Ingenieria en Informatica",
    "Ingenieria Civil Informatica",
    "Licenciatura en Sistemas",
    "Tecnicatura en Programacion",
    "Ingenieria en Computacion",
    "Maestria en Ingenieria de Software",
    "Licenciatura en Ciencias de Datos",
    "Analista de Sistemas",
]

# Honorificos que aparecen en la prosa pero NO en el gold de nombre.
HONORIFICS: list[str] = ["Ing.", "Lic.", "Dr.", "Dra.", "Mg."]

# Combos de otros idiomas (ademas del ingles) para variedad de extraccion.
# La clave es el pais; el ingles se agrega aparte en gold/render.
PORTUGUESE = (("portugues", "nativo"),)
EXTRA_LANGS: list[tuple[tuple[str, str], ...]] = [
    (),
    (("frances", "b1"),),
    (("italiano", "a2"),),
    (("aleman", "b1"),),
]

# Frases de objetivo. Fraseo fiel a modelos_cv (estructura "rol + N años +
# Buscando..."). {y}=años, {disc}=disciplina legible, {sector}, {lang}, {fw}, {db}.
OBJECTIVE_TEMPLATES: list[str] = [
    "{disc_cap} orientado a resultados con mas de {y} años de experiencia en la "
    "construccion de aplicaciones web escalables. Buscando aprovechar mi experiencia "
    "en {lang} y tecnologias en la nube para impulsar la innovacion en una empresa "
    "con vision de futuro.",
    "{sen} consumado con mas de {y} años de experiencia en ingenieria de software y "
    "liderazgo de equipos. Buscando aprovechar mi experiencia en {lang} y {fw} para "
    "impulsar proyectos impactantes.",
    "Profesional de {disc} orientado a los detalles con {y} años de experiencia en "
    "desarrollo de software. Deseoso de contribuir a proyectos innovadores con {lang} "
    "y mejorar mis habilidades en un entorno colaborativo.",
    "{disc_cap} con {y} años de experiencia y una solida base en {lang}. Buscando un "
    "rol desafiante para aprovechar mis habilidades en {fw} y el diseño de APIs sobre {db}.",
    "{disc_cap} orientado a resultados con {y} años de experiencia en la industria "
    "{sector}. Buscando aprovechar mis habilidades en el desarrollo de aplicaciones "
    "seguras y eficientes con {lang}.",
]

# Bullets por disciplina. Fraseo fiel a modelos_cv (incluye metricas de impacto).
# render elige 2-4 por puesto. {fw}/{db} se sustituyen por el stack del candidato.
BULLETS: dict[str, list[str]] = {
    "backend": [
        "Lidere el desarrollo de una arquitectura de microservicios para una plataforma "
        "de gran escala.",
        "Implemente pipelines de CI/CD utilizando Jenkins y Docker para agilizar los "
        "procesos de despliegue.",
        "Mentorie a desarrolladores junior y realice revisiones de codigo para asegurar "
        "las mejores practicas.",
        "Desarrolle y mantuve aplicaciones web utilizando {fw} y APIs RESTful.",
        "Cree APIs RESTful para varias aplicaciones, mejorando la accesibilidad e "
        "integracion de datos.",
        "Optimice el rendimiento a traves de la refactorizacion de codigo y la "
        "indexacion de {db}.",
        "Escribi pruebas unitarias para asegurar la calidad y confiabilidad del codigo.",
        "Implemente medidas de cifrado y seguridad para proteger informacion sensible.",
    ],
    "frontend": [
        "Desarrolle y mantuve aplicaciones web utilizando Django y React, mejorando el "
        "compromiso del usuario en un 30%.",
        "Colabore con diseñadores UX/UI para implementar diseños responsivos y mejorar "
        "la experiencia del usuario.",
        "Optimice el rendimiento de la aplicacion a traves de la refactorizacion de "
        "codigo y la indexacion de bases de datos.",
        "Integre el frontend con APIs RESTful y servicios de backend.",
    ],
    "data_science": [
        "Desarrolle modelos predictivos utilizando Scikit-learn para pronosticar "
        "tendencias de ventas, resultando en un aumento del 15% en ingresos.",
        "Colabore con ingenieros de datos para diseñar procesos ETL para la extraccion "
        "y transformacion de datos.",
        "Cree paneles interactivos utilizando Tableau para visualizar indicadores clave "
        "de rendimiento.",
        "Diseñe e implemente modelos de aprendizaje automatico para analisis predictivo, "
        "mejorando los procesos de toma de decisiones.",
        "Preprocese y analice grandes conjuntos de datos utilizando Pandas y NumPy.",
        "Desplegue modelos de aprendizaje automatico en produccion utilizando AWS SageMaker.",
    ],
    "devops": [
        "Automatice procesos de despliegue utilizando Jenkins y Docker, reduciendo el "
        "tiempo de despliegue en un 50%.",
        "Implemente infraestructura como codigo (IaC) utilizando Terraform, mejorando "
        "la escalabilidad y confiabilidad.",
        "Colabore con equipos de desarrollo para asegurar la integracion fluida de "
        "aplicaciones.",
        "Administre clusters de Kubernetes y monitoreo con Prometheus.",
    ],
    "mobile": [
        "Desarrolle apps nativas Android/Kotlin publicadas en Play Store.",
        "Implemente arquitectura MVVM y consumo de APIs REST.",
        "Optimice el uso de memoria y bateria de la aplicacion.",
    ],
    "qa": [
        "Diseñe suites de pruebas automatizadas con Selenium y scripts en Python.",
        "Implemente pruebas de regresion en el pipeline de CI.",
        "Reporte y di seguimiento a defectos junto al equipo de desarrollo.",
    ],
    "pm": [
        "Lidere el roadmap de producto coordinando equipos de ingenieria y diseño.",
        "Defini metricas de exito y prioridades junto a stakeholders.",
        "Gestione el backlog y ceremonias agiles del equipo.",
    ],
    "embedded": [
        "Desarrolle firmware en C/C++ para microcontroladores ARM.",
        "Implemente drivers y protocolos de comunicacion sobre RTOS.",
        "Optimice el consumo energetico de dispositivos IoT.",
    ],
}

# Proyectos por disciplina. Nombres y descripciones fieles a modelos_cv.
PROJECTS: dict[str, list[tuple[str, str]]] = {
    "backend": [
        (
            "Plataforma de Comercio Electronico",
            "Arquitecte y desarrolle una plataforma escalable utilizando {fw} y AWS, "
            "manejando miles de usuarios concurrentes.",
        ),
        (
            "Aplicacion Nativa de la Nube",
            "Diseñe e implemente una aplicacion nativa de la nube utilizando {fw} y "
            "Kubernetes, logrando una reduccion del 40% en costos operativos.",
        ),
        (
            "Tuberia de Procesamiento de Datos",
            "Desarrolle una tuberia de procesamiento utilizando Python y Apache Kafka, "
            "habilitando analisis de datos en tiempo real.",
        ),
        (
            "Aplicacion de Banca en Linea",
            "Diseñe una plataforma de banca en linea utilizando {fw}, gestionando "
            "cuentas y transacciones de forma segura.",
        ),
    ],
    "frontend": [
        (
            "Plataforma de Aprendizaje en Linea",
            "Cree una plataforma full-stack utilizando Django y React, permitiendo "
            "inscripcion a cursos y seguimiento de progreso.",
        ),
        (
            "Aplicacion de Blog",
            "Desarrolle una plataforma de blogs con autenticacion de usuarios y gestion "
            "de contenido.",
        ),
    ],
    "data_science": [
        (
            "Segmentacion de Clientes",
            "Implemente algoritmos de agrupamiento para segmentar clientes segun su "
            "comportamiento de compra, mejorando las estrategias de marketing dirigidas.",
        ),
        (
            "Modelo de Pronostico de Ventas",
            "Construi un modelo de series temporales utilizando Python y ARIMA, "
            "mejorando la gestion de inventarios.",
        ),
        (
            "Modelo de Clasificacion de Imagenes",
            "Desarrolle una red neuronal convolucional (CNN), logrando un 95% de "
            "precision en los datos de prueba.",
        ),
    ],
    "devops": [
        (
            "Implementacion de Pipeline de CI/CD",
            "Diseñe e implemente un pipeline de CI/CD para una arquitectura de "
            "microservicios, mejorando la frecuencia de despliegue.",
        ),
        (
            "Sistema de Monitoreo",
            "Desarrolle un sistema de monitoreo utilizando Python y Prometheus para "
            "rastrear el rendimiento y tiempo de actividad de la aplicacion.",
        ),
    ],
    "mobile": [("App de Delivery", "Aplicacion Android con tracking en tiempo real.")],
    "qa": [("Framework de Automatizacion", "Suite de regresion E2E con Selenium.")],
    "pm": [("Lanzamiento de Producto", "Coordinacion del go-to-market de una nueva linea.")],
    "embedded": [("Nodo IoT", "Dispositivo de telemetria con firmware de bajo consumo.")],
}

CERTIFICATIONS: dict[str, list[str]] = {
    "backend": ["AWS Solutions Architect - Associate", "Certified Kubernetes Administrator (CKA)"],
    "frontend": ["Meta Front-End Developer (Coursera)"],
    "data_science": ["TensorFlow Developer Certificate", "Professional Data Scientist (edX)"],
    "devops": ["AWS DevOps Engineer - Professional", "Terraform Associate"],
    "mobile": ["Associate Android Developer (Google)"],
    "qa": ["ISTQB Certified Tester"],
    "pm": ["Professional Scrum Master I (PSM I)"],
    "embedded": ["Certified ARM Embedded Systems"],
}

# Lineas basura realistas (ruido de distraccion no informativo).
JUNK_LINES: list[str] = [
    "Hobbies: ajedrez, running (mejor marca 3h45 en maraton) y fotografia.",
    "Referencias disponibles a pedido.",
    "Disponibilidad inmediata. Abierto a modalidad remota.",
    "Voluntario en comunidades de software libre los fines de semana.",
    "Me apasiona el clean code y la mentoria de equipos.",
    "Padre de dos hijos. Fanatico del mate y el asado de los domingos.",
    "Certificado en primeros auxilios. Licencia de conducir vigente.",
]

# Disciplina -> etiqueta legible para objetivo/encabezado.
DISCIPLINE_LABEL: dict[str, str] = {
    "backend": "desarrollo backend",
    "frontend": "desarrollo frontend",
    "data_science": "ciencia de datos",
    "devops": "DevOps e infraestructura",
    "mobile": "desarrollo mobile",
    "qa": "QA y automatizacion",
    "pm": "gestion de producto",
    "embedded": "sistemas embebidos",
    "fullstack": "desarrollo full stack",
}

# Disciplina -> titulo de rol para experiencias.
ROLE_TITLES: dict[str, list[str]] = {
    "backend": [
        "Backend Engineer", "Desarrollador Backend Senior", "Ingeniero de Software Backend",
    ],
    "frontend": ["Frontend Developer", "Desarrollador Frontend"],
    "data_science": ["Data Scientist", "Cientifico de Datos"],
    "devops": ["DevOps Engineer", "Ingeniero DevOps / SRE"],
    "mobile": ["Mobile Developer", "Desarrollador Android"],
    "qa": ["QA Automation Engineer", "Analista de QA"],
    "pm": ["Product Manager", "Gerente de Producto"],
    "embedded": ["Firmware Engineer", "Ingeniero de Sistemas Embebidos"],
    "fullstack": ["Full Stack Engineer", "Desarrollador Full Stack"],
}

COMPANIES: list[str] = [
    "TechNova", "DataPagos", "CloudFin", "MercadoStack", "Logix", "Pagosur",
    "ByteForge", "Nubeles", "Quantio", "RetailHub", "SaludTech", "EduPlatform",
]

# Pool de nombres (unicos). El email se deriva del nombre en builder.py.
NAMES: list[str] = [
    "Martin Gomez", "Lucia Fernandez", "Carlos Ruiz", "Ana Paula Souza",
    "Diego Torres", "Rodrigo Mendes", "Sofia Ramirez", "Gabriel Silva",
    "Valentina Lopez", "Pedro Alvarez", "Marta Gil", "Juan David Moreno",
    "Bruno Costa", "Camila Herrera", "Nicolas Pereyra", "Andrea Nunez",
    "Felipe Vargas", "Esteban Diaz", "Paula Castro", "Ricardo Gomez",
    "Mariana Lopez", "Jorge Ramos", "Tomas Aguirre", "Laura Mendez",
    "Sebastian Rios", "Carolina Fuentes", "Hernan Vega", "Mariano Castro",
    "Daniela Ortiz", "Ignacio Funes", "Renata Lima", "Oscar Mendez",
    "Patricia Rojas", "Joao Almeida", "Monica Salas", "Bruno Tavares",
    "Veronica Luna", "Emilia Rojas", "Javier Molina", "Lucas Benitez",
    "Romina Caceres", "Damian Ferreyra", "Nora Santillan", "Bruno Salazar",
    "Cecilia Bustos", "Hector Pineda", "Valeria Ocampo", "Raul Esquivel",
    "Florencia Vidal", "Ignacio Ferrer", "Tomas Bianchi", "Paula Miranda",
    "Lorena Cabrera", "Emanuel Rios", "Gregorio Paz", "Renan Carvalho",
    "Daniela Pizarro", "Mauricio Leon", "Constanza Rivas", "Agustin Peralta",
    "Florencia Sosa", "Joaquin Aravena", "Ines Mora", "Pablo Gimenez",
    "Camila Torres", "Andres Vargas", "Gabriela Nunez", "Federico Aguilar",
]

ENGLISH_PHRASES: dict[str, str] = {
    "a2": "Ingles basico (A2), en mejora.",
    "b1": "Ingles intermedio (B1).",
    "b2": "Ingles B2 (lectura tecnica y reuniones).",
    "c1": "Ingles avanzado (C1).",
    "c2": "Ingles C2, casi nativo.",
    "nativo": "Ingles nativo.",
}
