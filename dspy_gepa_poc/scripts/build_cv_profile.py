"""Construye cv_profile.csv: 16 CVs originales (con 5 columnas nuevas anotadas) + 17 sinteticos."""

import csv
from pathlib import Path

HEADER = [
    "split",
    "text",
    "nombre",
    "email",
    "años_experiencia",
    "skills",
    "educacion_principal",
    "seniority_declarado",
    "stack_principal",
    "idiomas",
    "ubicacion",
    "industria_previa",
]

ORIGINALS = [
    (
        "train",
        "JUAN PÉREZ\njuan.perez@email.com\n\nEXPERIENCIA: 5 años en desarrollo de software\n\nHABILIDADES:\n• Python\n• Machine Learning\n• Docker\n• AWS\n\nEDUCACIÓN:\nLicenciatura en Ciencias de la Computación, UNAM, 2018",  # noqa: E501
        "Juan Pérez",
        "juan.perez@email.com",
        "5",
        "Python, Machine Learning, Docker, AWS",
        "Licenciatura Ciencias Computación, UNAM",  # noqa: E501
        "",
        "Python; Machine Learning; Docker; AWS",
        "",
        "",
        "",
    ),
    (
        "train",
        "María González (maria.g@company.com) es una desarrolladora senior con más de 8 años de experiencia en desarrollo web. Competente en React, Node.js y AWS. Graduada de la Universidad de Madrid con Maestría en Ingeniería en Computación en 2015.",  # noqa: E501
        "María González",
        "maria.g@company.com",
        "8",
        "React, Node.js, AWS",
        "Maestría Ingeniería Computación, Universidad Madrid",  # noqa: E501
        "senior",
        "React; Node.js; AWS",
        "",
        "",
        "",
    ),
    (
        "train",
        "ROBERTO CHEN\nEmail: r.chen@techcorp.com\n\nHistorial Laboral: Ingeniero de Software (2019-2024)\nHabilidades Técnicas: Java, Spring Boot, Kubernetes, PostgreSQL\n\nEducación: Licenciatura en Ciencias en Tecnología de la Información\nUniversidad de California, Berkeley",  # noqa: E501
        "Roberto Chen",
        "r.chen@techcorp.com",
        "5",
        "Java, Spring Boot, Kubernetes, PostgreSQL",
        "Licenciatura Ciencias Tecnología Información, UC Berkeley",  # noqa: E501
        "",
        "Java; Spring Boot; Kubernetes; PostgreSQL",
        "",
        "",
        "",
    ),
    (
        "train",
        "Sara Williams | sarah.w@devmail.com\n\nResumen Profesional:\n- 10 años exp en ciencia de datos\n- Experta en Python, R, TensorFlow, scikit-learn\n\nEducación:\n- PhD Ciencia de Datos, Stanford (2013)",  # noqa: E501
        "Sara Williams",
        "sarah.w@devmail.com",
        "10",
        "Python, R, TensorFlow, scikit-learn",
        "PhD Ciencia de Datos, Stanford",  # noqa: E501
        "",
        "Python; R; TensorFlow; scikit-learn",
        "",
        "",
        "Ciencia de Datos",
    ),
    (
        "train",
        "AHMED HASSAN\nContacto: ahmed.hassan@email.net\n\nEXPERIENCIA PROFESIONAL\nIngeniero DevOps - 2021 a Presente (3 años)\nResponsable de pipelines CI/CD usando Jenkins y Docker.\nDesplegó aplicaciones en Kubernetes y administró infraestructura cloud con Terraform.\n\nEDUCACIÓN\nMSc Ciencias de la Computación, Universidad de Toronto, 2020",  # noqa: E501
        "Ahmed Hassan",
        "ahmed.hassan@email.net",
        "3",
        "Jenkins, Docker, Kubernetes, Terraform",
        "MSc Ciencias Computación, Universidad Toronto",  # noqa: E501
        "",
        "Jenkins; Docker; Kubernetes; Terraform",
        "",
        "",
        "DevOps",
    ),
    (
        "train",
        "Jennifer López\nj.lopez@marketing.com\n\nExperiencia: Gerente de Marketing desde 2017 (7 años)\nCompetencias clave: SEO, Google Analytics, Estrategia de Contenido, Redes Sociales\n\nFormación Académica: Licenciatura Marketing, NYU",  # noqa: E501
        "Jennifer López",
        "j.lopez@marketing.com",
        "7",
        "SEO, Google Analytics, Estrategia de Contenido, Redes Sociales",
        "Licenciatura Marketing, NYU",  # noqa: E501
        "",
        "SEO; Google Analytics; Estrategia de Contenido; Redes Sociales",
        "",
        "",
        "Marketing",
    ),
    (
        "train",
        "Miguel Brown <m.brown@consultant.com>\n\nHistorial de Carrera:\n• Consultor Senior (2020-2024): 4 años\n• Analista (2018-2020): 2 años\nTotal: 6 años\n\nHabilidades: Excel, Tableau, SQL, Power BI\n\nEducación: MBA, Harvard Business School, 2018",  # noqa: E501
        "Miguel Brown",
        "m.brown@consultant.com",
        "6",
        "Excel, Tableau, SQL, Power BI",
        "MBA, Harvard Business School",  # noqa: E501
        "senior",
        "Excel; Tableau; SQL; Power BI",
        "",
        "",
        "Consultoría",
    ),
    (
        "train",
        "Emma Watson\nemma.watson@design.io\n\nDiseñadora UX | 4 años de experiencia\nHabilidades: Figma, Adobe XD, Investigación de Usuarios, Prototipado\nTítulo: BFA Diseño Gráfico, RISD",  # noqa: E501
        "Emma Watson",
        "emma.watson@design.io",
        "4",
        "Figma, Adobe XD, Investigación de Usuarios, Prototipado",
        "BFA Diseño Gráfico, RISD",  # noqa: E501
        "",
        "Figma; Adobe XD; Investigación de Usuarios; Prototipado",
        "",
        "",
        "Diseño UX",
    ),
    (
        "val",
        "David Kim\ndavidkim@techstart.com\n\nDesarrollador Full Stack - 6 años\nStack Tecnológico: JavaScript, React, Node.js, MongoDB, GraphQL\n\nEducación: Licenciatura Ingeniería de Software, Georgia Tech (2018)",  # noqa: E501
        "David Kim",
        "davidkim@techstart.com",
        "6",
        "JavaScript, React, Node.js, MongoDB, GraphQL",
        "Licenciatura Ingeniería Software, Georgia Tech",  # noqa: E501
        "",
        "JavaScript; React; Node.js; MongoDB; GraphQL",
        "",
        "",
        "",
    ),
    (
        "val",
        "Lisa Anderson | lisa.a@sales.com\n\nEjecutiva de Ventas con más de 12 años en ventas B2B de software. Experiencia en CRM (Salesforce), Generación de Leads y Negociación de Contratos. MBA de Wharton, 2011.",  # noqa: E501
        "Lisa Anderson",
        "lisa.a@sales.com",
        "12",
        "Salesforce, Generación de Leads, Negociación de Contratos",
        "MBA, Wharton",  # noqa: E501
        "",
        "Salesforce; Generación de Leads; Negociación de Contratos",
        "",
        "",
        "Ventas B2B Software",
    ),  # noqa: E501
    (
        "val",
        "THOMAS MILLER\nthomas.miller@cloudeng.com\n\nArquitecto Cloud (2019-presente)\nAños de Experiencia: 5\nTecnologías: AWS, Azure, GCP, Terraform, Ansible\n\nFormación: MS Computación en la Nube, Universidad Carnegie Mellon",  # noqa: E501
        "Thomas Miller",
        "thomas.miller@cloudeng.com",
        "5",
        "AWS, Azure, GCP, Terraform, Ansible",
        "MS Computación Nube, Carnegie Mellon",  # noqa: E501
        "",
        "AWS; Azure; GCP; Terraform; Ansible",
        "",
        "",
        "Cloud Computing",
    ),
    (
        "val",
        "Sophia Rodríguez\nContacto: sophia.r@biotech.org\n\nCientífica de Investigación - Bioinformática\nExperiencia: 9 años (2015-2024)\nHabilidades: Python, R, BioConductor, Análisis NGS\n\nPhD Biología Computacional, Johns Hopkins, 2015",  # noqa: E501
        "Sophia Rodríguez",
        "sophia.r@biotech.org",
        "9",
        "Python, R, BioConductor, Análisis NGS",
        "PhD Biología Computacional, Johns Hopkins",  # noqa: E501
        "",
        "Python; R; BioConductor; Análisis NGS",
        "",
        "",
        "Biotech",
    ),
    (
        "val",
        "James Taylor <j.taylor@finance.net>\n\nAnalista Cuantitativo | 7 años\nCompetente en: Python, C++, Modelado Financiero, Análisis de Riesgo\n\nEducado en: MSc Ingeniería Financiera, Universidad de Columbia (2017)",  # noqa: E501
        "James Taylor",
        "j.taylor@finance.net",
        "7",
        "Python, C++, Modelado Financiero, Análisis de Riesgo",
        "MSc Ingeniería Financiera, Universidad Columbia",  # noqa: E501
        "",
        "Python; C++; Modelado Financiero; Análisis de Riesgo",
        "",
        "",
        "Finanzas",
    ),
    (
        "test",
        "Anna Kowalski\n📧 anna.kowalski@pm.com\n\nGerente de Producto @ TechCorp\n🕐 8 años en gestión de producto\n\nHabilidades Clave: Agile, JIRA, Planificación de Roadmap, Historias de Usuario\n\n🎓 MBA Gestión de Producto, Northwestern Kellogg, 2016",  # noqa: E501
        "Anna Kowalski",
        "anna.kowalski@pm.com",
        "8",
        "Agile, JIRA, Planificación de Roadmap, Historias de Usuario",
        "MBA Gestión de Producto, Northwestern Kellogg",  # noqa: E501
        "",
        "Agile; JIRA; Planificación de Roadmap; Historias de Usuario",
        "",
        "",
        "Gestión de Producto",
    ),  # noqa: E501
    (
        "test",
        "Carlos Méndez | carlos@dev.mx | Dev Backend | 5a exp\nStack: Go, Microservicios, gRPC, Kubernetes\nLic. CS, UNAM 2019",  # noqa: E501
        "Carlos Méndez",
        "carlos@dev.mx",
        "5",
        "Go, Microservicios, gRPC, Kubernetes",
        "Lic. CS, UNAM",
        "",
        "Go; Microservicios; gRPC; Kubernetes",
        "",
        "",
        "Backend",
    ),
    (
        "test",
        "La Dra. Elena Petrov (elena.petrov@research.edu) ha dedicado 15 años a la investigación en inteligencia artificial. Su experiencia abarca Aprendizaje Profundo, NLP, Visión por Computadora y Aprendizaje por Refuerzo. Obtuvo su PhD en Inteligencia Artificial del MIT en 2009.",  # noqa: E501
        "Elena Petrov",
        "elena.petrov@research.edu",
        "15",
        "Aprendizaje Profundo, NLP, Visión por Computadora, Aprendizaje por Refuerzo",
        "PhD Inteligencia Artificial, MIT",  # noqa: E501
        "",
        "Aprendizaje Profundo; NLP; Visión por Computadora; Aprendizaje por Refuerzo",
        "",
        "",
        "Investigación AI",
    ),  # noqa: E501
]

NEW = [
    # === 5 FIT_ALTO ===
    (
        "train",
        "MARTÍN ACOSTA\nmartin.acosta@dev.com.ar | Buenos Aires, Argentina\n\nDesarrollador Backend Senior - 7 años\n\nEXPERIENCIA:\n• Tech Lead Backend en fintech (2021-presente)\n• Backend Engineer en e-commerce (2017-2021)\n\nSTACK PRINCIPAL:\n- Python (7 años), FastAPI (4 años)\n- PostgreSQL, Redis, Docker, Kubernetes, AWS\n- Microservicios, CI/CD con GitHub Actions\n\nIDIOMAS: Español (nativo), Inglés (B2)\n\nEDUCACIÓN: Ingeniería en Informática, UBA, 2017",  # noqa: E501
        "Martín Acosta",
        "martin.acosta@dev.com.ar",
        "7",
        "Python, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, AWS, Microservicios, CI/CD",
        "Ingeniería en Informática, UBA",  # noqa: E501
        "senior",
        "Python:7; FastAPI:4; PostgreSQL; Docker; Kubernetes; AWS",
        "español:nativo; inglés:b2",
        "Buenos Aires, Argentina",
        "Fintech",
    ),  # noqa: E501
    (
        "train",
        "Lucía Fernández\nlucia.fernandez@correo.mx | Ciudad de México\n\nSenior Backend Developer (Django) - 6 años\n\nExperiencia: Desarrollo de plataforma e-commerce escalable. Liderazgo técnico de equipo de 4 personas.\n\nStack: Python, Django, Django REST Framework, PostgreSQL, Docker, AWS (ECS, RDS, S3), Celery, Redis\n\nIdiomas: Español nativo, Inglés C1 (certificado IELTS 7.5)\n\nFormación: Licenciatura en Ingeniería de Software, ITESM, 2018",  # noqa: E501
        "Lucía Fernández",
        "lucia.fernandez@correo.mx",
        "6",
        "Python, Django, Django REST Framework, PostgreSQL, Docker, AWS, Celery, Redis",
        "Licenciatura Ingeniería de Software, ITESM",  # noqa: E501
        "senior",
        "Python:6; Django:6; PostgreSQL; Docker; AWS",
        "español:nativo; inglés:c1",
        "Ciudad de México, México",
        "E-commerce",
    ),  # noqa: E501
    (
        "train",
        "DIEGO RAMÍREZ\ndiego.ramirez@saas.co | Medellín, Colombia\n\nBackend Engineer - 5 años de experiencia\n\nEMPRESAS: SaaS B2B (analytics) desde 2020\n\nHABILIDADES TÉCNICAS:\n- Python 3, FastAPI, SQLAlchemy\n- PostgreSQL, Docker, Kubernetes\n- AWS (EKS, RDS, Lambda)\n- Arquitectura de microservicios\n\nIDIOMAS: Español (nativo) | Inglés (B2, TOEFL 95)\n\nEducación: Ing. de Sistemas, Universidad EAFIT, 2019",  # noqa: E501
        "Diego Ramírez",
        "diego.ramirez@saas.co",
        "5",
        "Python, FastAPI, SQLAlchemy, PostgreSQL, Docker, Kubernetes, AWS, Microservicios",
        "Ingeniería de Sistemas, Universidad EAFIT",  # noqa: E501
        "",
        "Python:5; FastAPI:5; PostgreSQL; Docker; Kubernetes; AWS",
        "español:nativo; inglés:b2",
        "Medellín, Colombia",
        "SaaS B2B",
    ),  # noqa: E501
    (
        "val",
        "Florencia Sosa\nflorencia.sosa@fintech.uy\nMontevideo, Uruguay\n\nTech Lead Backend - 8 años\n\nTrayectoria en fintech regional: pagos, billeteras virtuales, integraciones bancarias.\n\nTecnologías: Python, Django, FastAPI, PostgreSQL, Docker, Kubernetes, AWS, RabbitMQ, gRPC\n\nIdiomas: Español nativo, Inglés B2\n\nEstudios: Licenciatura en Computación, UdelaR, 2016",  # noqa: E501
        "Florencia Sosa",
        "florencia.sosa@fintech.uy",
        "8",
        "Python, Django, FastAPI, PostgreSQL, Docker, Kubernetes, AWS, RabbitMQ, gRPC",
        "Licenciatura en Computación, UdelaR",  # noqa: E501
        "lead",
        "Python:8; Django; FastAPI; PostgreSQL; Docker; Kubernetes; AWS",
        "español:nativo; inglés:b2",
        "Montevideo, Uruguay",
        "Fintech",
    ),  # noqa: E501
    (
        "test",
        "ANDRÉS VARGAS\nandres.vargas@ecomm.cl | Santiago de Chile\n\nSenior Backend Developer | 6 años\n\nExperiencia profesional en e-commerce de alto tráfico (>1M pedidos/mes).\n\nStack: Python, FastAPI, PostgreSQL, Docker, Kubernetes, microservicios, Redis, Kafka.\n\nIdiomas: Español (nativo), Inglés (C1).\n\nFormación: Ingeniería Civil Informática, Universidad de Chile, 2018",  # noqa: E501
        "Andrés Vargas",
        "andres.vargas@ecomm.cl",
        "6",
        "Python, FastAPI, PostgreSQL, Docker, Kubernetes, Microservicios, Redis, Kafka",
        "Ingeniería Civil Informática, Universidad de Chile",  # noqa: E501
        "senior",
        "Python:6; FastAPI:6; PostgreSQL; Docker; Kubernetes",
        "español:nativo; inglés:c1",
        "Santiago, Chile",
        "E-commerce",
    ),  # noqa: E501
    # === 4 FIT_MEDIO ===
    (
        "train",
        "Pablo Giménez\npablo.gimenez@correo.com.ar | Buenos Aires\n\nDesarrollador Backend Senior - 6 años en fintech argentino\n\nStack: Python, Django, PostgreSQL, Docker, AWS\n\nIdiomas: Español nativo, Inglés básico (A2, en formación)\n\nEducación: Licenciatura en Sistemas, UTN, 2018",  # noqa: E501
        "Pablo Giménez",
        "pablo.gimenez@correo.com.ar",
        "6",
        "Python, Django, PostgreSQL, Docker, AWS",
        "Licenciatura en Sistemas, UTN",  # noqa: E501
        "senior",
        "Python:6; Django; PostgreSQL; Docker; AWS",
        "español:nativo; inglés:a2",
        "Buenos Aires, Argentina",
        "Fintech",
    ),  # noqa: E501
    (
        "train",
        "Inés Mora\nines.mora@tech.es\nMadrid, España\n\nSenior Backend Engineer - 7 años en SaaS\n\nExperta en Python, FastAPI, PostgreSQL, Docker, Kubernetes, AWS.\n\nIdiomas: Español nativo, Inglés B2.\n\nMáster en Ingeniería Informática, Universidad Politécnica de Madrid, 2017",  # noqa: E501
        "Inés Mora",
        "ines.mora@tech.es",
        "7",
        "Python, FastAPI, PostgreSQL, Docker, Kubernetes, AWS",
        "Máster Ingeniería Informática, UPM",  # noqa: E501
        "senior",
        "Python:7; FastAPI; PostgreSQL; Docker; Kubernetes; AWS",
        "español:nativo; inglés:b2",
        "Madrid, España",
        "SaaS",
    ),  # noqa: E501
    (
        "val",
        "Tomás Herrera\ntomas.herrera@dev.com.ar | Córdoba, Argentina\n\nDesarrollador Backend Junior - 2 años\n\nHe trabajado con: Python, FastAPI, PostgreSQL, Docker, Git.\n\nIdiomas: Español nativo, Inglés B1.\n\nEstudiante avanzado de Ingeniería en Sistemas, UNC. Bootcamp Backend Python 2022.",  # noqa: E501
        "Tomás Herrera",
        "tomas.herrera@dev.com.ar",
        "2",
        "Python, FastAPI, PostgreSQL, Docker, Git",
        "Ingeniería en Sistemas, UNC (en curso); Bootcamp Backend Python",  # noqa: E501
        "junior",
        "Python:2; FastAPI; PostgreSQL; Docker",
        "español:nativo; inglés:b1",
        "Córdoba, Argentina",
        "",
    ),  # noqa: E501
    (
        "val",
        "Camila Torres\ncamila.torres@shop.mx | Guadalajara, México\n\nDesarrolladora Backend - 5 años en e-commerce regional\n\nTecnologías: Python, Flask, PostgreSQL, MySQL, AWS EC2, Git.\nExperiencia en mantenimiento de APIs y desarrollo de features.\n\nIdiomas: Español nativo, Inglés B2.\n\nEducación: Ingeniería en Computación, UDG, 2019",  # noqa: E501
        "Camila Torres",
        "camila.torres@shop.mx",
        "5",
        "Python, Flask, PostgreSQL, MySQL, AWS, Git",
        "Ingeniería en Computación, UDG",  # noqa: E501
        "",
        "Python:5; Flask:5; PostgreSQL; MySQL; AWS",
        "español:nativo; inglés:b2",
        "Guadalajara, México",
        "E-commerce",
    ),  # noqa: E501
    # === 8 NO_FIT ===
    (
        "train",
        "Nicolás Bravo\nnicolas.bravo@frontend.com.ar | Buenos Aires\n\nSenior Frontend Developer - 7 años\n\nStack: React, TypeScript, Next.js, Tailwind CSS, Redux, Vite.\n\nIdiomas: Español nativo, Inglés B2.\n\nLicenciatura en Sistemas, UADE, 2017",  # noqa: E501
        "Nicolás Bravo",
        "nicolas.bravo@frontend.com.ar",
        "7",
        "React, TypeScript, Next.js, Tailwind CSS, Redux, Vite",
        "Licenciatura en Sistemas, UADE",  # noqa: E501
        "senior",
        "React:7; TypeScript; Next.js; Redux",
        "español:nativo; inglés:b2",
        "Buenos Aires, Argentina",
        "Frontend",
    ),  # noqa: E501
    (
        "train",
        "Romina Espinosa\nromina.espinosa@web.mx | CDMX\n\nFrontend Engineer - 5 años\n\nVue.js, Nuxt, JavaScript, CSS3, Figma (handoff), pruebas con Cypress.\n\nIdiomas: Español nativo, Inglés B1.\n\nIngeniería en Sistemas Computacionales, IPN, 2019",  # noqa: E501
        "Romina Espinosa",
        "romina.espinosa@web.mx",
        "5",
        "Vue.js, Nuxt, JavaScript, CSS3, Figma, Cypress",
        "Ingeniería en Sistemas Computacionales, IPN",  # noqa: E501
        "",
        "Vue.js:5; Nuxt; JavaScript",
        "español:nativo; inglés:b1",
        "Ciudad de México, México",
        "Frontend",
    ),  # noqa: E501
    (
        "train",
        "Sebastián Pino\nsebastian.pino@rails.cl | Santiago, Chile\n\nDesarrollador Backend Ruby on Rails - 6 años\n\nTecnologías: Ruby, Ruby on Rails, PostgreSQL, Sidekiq, Heroku, RSpec.\n\nIdiomas: Español nativo, Inglés B2.\n\nIngeniería Civil Informática, PUC, 2018",  # noqa: E501
        "Sebastián Pino",
        "sebastian.pino@rails.cl",
        "6",
        "Ruby, Ruby on Rails, PostgreSQL, Sidekiq, Heroku, RSpec",
        "Ingeniería Civil Informática, PUC",  # noqa: E501
        "",
        "Ruby:6; Ruby on Rails:6; PostgreSQL",
        "español:nativo; inglés:b2",
        "Santiago, Chile",
        "Backend",
    ),  # noqa: E501
    (
        "train",
        "Verónica Castro\nveronica.castro@laravel.co | Bogotá, Colombia\n\nDesarrolladora Backend PHP - 8 años\n\nStack: PHP, Laravel, MySQL, jQuery, Apache, Linux.\n\nIdiomas: Español nativo, Inglés A2.\n\nIngeniería de Sistemas, Universidad Nacional de Colombia, 2016",  # noqa: E501
        "Verónica Castro",
        "veronica.castro@laravel.co",
        "8",
        "PHP, Laravel, MySQL, jQuery, Apache, Linux",
        "Ingeniería de Sistemas, Universidad Nacional de Colombia",  # noqa: E501
        "senior",
        "PHP:8; Laravel:8; MySQL",
        "español:nativo; inglés:a2",
        "Bogotá, Colombia",
        "Backend",
    ),  # noqa: E501
    (
        "train",
        "Mateo Salinas\nmateo.salinas@ios.com.ar | Buenos Aires\n\niOS Developer - 5 años\n\nSwift, SwiftUI, UIKit, Combine, Core Data, Xcode, TestFlight.\nPublicación de 6 apps en App Store.\n\nIdiomas: Español nativo, Inglés B2.\n\nLicenciatura en Sistemas, UTN, 2019",  # noqa: E501
        "Mateo Salinas",
        "mateo.salinas@ios.com.ar",
        "5",
        "Swift, SwiftUI, UIKit, Combine, Core Data, Xcode",
        "Licenciatura en Sistemas, UTN",  # noqa: E501
        "",
        "Swift:5; SwiftUI; UIKit",
        "español:nativo; inglés:b2",
        "Buenos Aires, Argentina",
        "Mobile iOS",
    ),  # noqa: E501
    (
        "val",
        "Gabriela Núñez\ngabriela.nunez@data.mx | Monterrey, México\n\nData Engineer Senior - 6 años\n\nTecnologías: Apache Spark, Hadoop, Airflow, Hive, AWS EMR, Python (PySpark), SQL.\nDiseño de pipelines ETL para 5TB diarios.\n\nIdiomas: Español nativo, Inglés B2.\n\nIngeniería en Sistemas, ITESM, 2018",  # noqa: E501
        "Gabriela Núñez",
        "gabriela.nunez@data.mx",
        "6",
        "Apache Spark, Hadoop, Airflow, Hive, AWS EMR, PySpark, SQL",
        "Ingeniería en Sistemas, ITESM",  # noqa: E501
        "senior",
        "Spark:6; Hadoop; Airflow; PySpark",
        "español:nativo; inglés:b2",
        "Monterrey, México",
        "Data Engineering",
    ),  # noqa: E501
    (
        "test",
        "Federico Aguilar\nfederico.aguilar@qa.com.ar | Rosario, Argentina\n\nQA Engineer - 5 años\n\nAutomatización con Selenium, Cypress, Postman, JMeter. Testing manual y exploratorio. Bug tracking en JIRA.\n\nIdiomas: Español nativo, Inglés B1.\n\nTecnicatura en Programación, UTN, 2019",  # noqa: E501
        "Federico Aguilar",
        "federico.aguilar@qa.com.ar",
        "5",
        "Selenium, Cypress, Postman, JMeter, JIRA, Testing Manual",
        "Tecnicatura en Programación, UTN",  # noqa: E501
        "",
        "Selenium:5; Cypress; Postman",
        "español:nativo; inglés:b1",
        "Rosario, Argentina",
        "QA",
    ),
    (
        "test",
        "Patricia Maldonado\npatricia.maldonado@pm.uy | Montevideo, Uruguay\n\nProject Manager / Scrum Master Certificada - 9 años\n\nCertificaciones: PMP, PSM-II.\nCompetencias: Agile, Scrum, Kanban, JIRA, Confluence, gestión de stakeholders.\n\nIdiomas: Español nativo, Inglés C1.\n\nLicenciatura en Administración, UCU, 2014",  # noqa: E501
        "Patricia Maldonado",
        "patricia.maldonado@pm.uy",
        "9",
        "Agile, Scrum, Kanban, JIRA, Confluence, Gestión de Stakeholders",
        "Licenciatura en Administración, UCU",  # noqa: E501
        "senior",
        "Agile; Scrum; JIRA",
        "español:nativo; inglés:c1",
        "Montevideo, Uruguay",
        "Gestión de Proyectos",
    ),  # noqa: E501
]

# === 12 CVs AMBIGUOS (diseñados para estresar al baseline) ===
# Fuentes de ambigüedad: fechas sin total, abreviaturas, skills enterrados en prosa,
# seniority contradictorio, idiomas implicitos, multi-idioma, ubicacion vaga,
# industria multiple, formato narrativo puro, distractores.
AMBIGUOUS = [
    (
        "train",
        "Diego Salgado | diego.salgado@dev.com.ar\n\nComencé como backend developer en 2018 en una fintech porteña. Durante esos años desarrollé APIs REST con FastAPI sobre PostgreSQL e implementé pipelines CI/CD con Docker. En 2023 me sumé como Tech Lead a un equipo SaaS B2B donde sigo hoy trabajando en microservicios sobre Kubernetes.\n\nNativo de español, inglés B2 (uso diario con HQ).\nResido en Buenos Aires, Argentina.\nEstudios: Ingeniería en Sistemas, UTN FRBA, 2017.",  # noqa: E501
        "Diego Salgado",
        "diego.salgado@dev.com.ar",
        "8",
        "Python, FastAPI, PostgreSQL, Docker, CI/CD, Kubernetes, Microservicios",
        "Ingeniería en Sistemas, UTN FRBA",  # noqa: E501
        "lead",
        "Python:8; FastAPI; PostgreSQL; Docker; Kubernetes",
        "español:nativo; inglés:b2",
        "Buenos Aires, Argentina",
        "Fintech",
    ),  # noqa: E501
    (
        "train",
        "Sofia Velez | sofia.velez@tech.mx\nSenior Backend Engineer | 3a exp\nStack: Python, FastAPI, PostgreSQL, Docker\nIdiomas: ES nativo, EN B2\nUbicación: Monterrey, MX\nEdu: Ing. en Sist. Computacionales, UANL",  # noqa: E501
        "Sofia Velez",
        "sofia.velez@tech.mx",
        "3",
        "Python, FastAPI, PostgreSQL, Docker",
        "Ingeniería en Sistemas Computacionales, UANL",  # noqa: E501
        "senior",
        "Python:3; FastAPI; PostgreSQL; Docker",
        "español:nativo; inglés:b2",
        "Monterrey, México",
        "Backend",
    ),  # noqa: E501
    (
        "train",
        "Karina Mendel\nkarina.mendel@research.io\n\nMi trayectoria profesional comenzó tras egresar del MIT en 2015 con un PhD en visión por computadora. Desde entonces he dedicado mi carrera a la investigación académica en deep learning, publicando más de 30 papers en conferencias top-tier (NeurIPS, ICML, CVPR). Mi expertise técnico incluye PyTorch, TensorFlow, distributed training y arquitecturas transformer.\nTrabajo desde Boston.",  # noqa: E501
        "Karina Mendel",
        "karina.mendel@research.io",
        "11",
        "PyTorch, TensorFlow, Distributed Training, Deep Learning, Visión por Computadora, Transformers",  # noqa: E501
        "PhD Visión por Computadora, MIT",  # noqa: E501
        "",
        "PyTorch; TensorFlow; Deep Learning",
        "",
        "Boston, Estados Unidos",
        "Investigación AI",
    ),
    (
        "train",
        "Joaquín Aravena\njoaquin.aravena@dev.cl\n\nIngeniero backend con 9 años de experiencia construyendo sistemas distribuidos. Mi camino comenzó en 2017 en un e-commerce regional escribiendo servicios en Python con Django; después de tres años pasé a una fintech donde implementé el motor de pagos sobre FastAPI y PostgreSQL, además de orquestar despliegues en Kubernetes vía Helm. Desde 2024 lidero la plataforma de un SaaS B2B donde uso Docker, AWS y Kafka.\nEspañol nativo, inglés C1.\nSantiago, Chile.\nIng. Civil Informática, Universidad de Chile, 2017.",  # noqa: E501
        "Joaquín Aravena",
        "joaquin.aravena@dev.cl",
        "9",
        "Python, Django, FastAPI, PostgreSQL, Kubernetes, Helm, Docker, AWS, Kafka, Sistemas Distribuidos",  # noqa: E501
        "Ingeniería Civil Informática, Universidad de Chile",  # noqa: E501
        "",
        "Python:9; Django; FastAPI; PostgreSQL; Docker; Kubernetes; AWS; Kafka",
        "español:nativo; inglés:c1",
        "Santiago, Chile",
        "Fintech",
    ),  # noqa: E501
    (
        "train",
        "Daniela Köhler | daniela.kohler@frontend.com.ar\nSenior Frontend Engineer with 6 years of experience.\nStack principal: React, TypeScript, Next.js, Tailwind, Vite.\nHobby: bouldering. Pets: 2 gatos. Coffee: oat milk.\nI love clean code and pair programming.\nSpanish native speaker, German A2, English C1.\nUbicación: Buenos Aires.\nEducation: Lic. en Sistemas, ITBA, 2019.",  # noqa: E501
        "Daniela Köhler",
        "daniela.kohler@frontend.com.ar",
        "6",
        "React, TypeScript, Next.js, Tailwind, Vite",
        "Licenciatura en Sistemas, ITBA",  # noqa: E501
        "senior",
        "React:6; TypeScript; Next.js; Tailwind; Vite",
        "español:nativo; inglés:c1; alemán:a2",
        "Buenos Aires, Argentina",
        "Frontend",
    ),  # noqa: E501
    (
        "train",
        "Hernán Cabezas\nhernan.cabezas@dev.com\n\nSenior backend developer, 7 años de experiencia.\nStack: Python, FastAPI, PostgreSQL, Docker, AWS.\nTrabajo de forma remota desde Latinoamérica.\nIdiomas: español nativo, inglés B2.\nEducación: Ingeniería en Computación, 2018.",  # noqa: E501
        "Hernán Cabezas",
        "hernan.cabezas@dev.com",
        "7",
        "Python, FastAPI, PostgreSQL, Docker, AWS",
        "Ingeniería en Computación",  # noqa: E501
        "senior",
        "Python:7; FastAPI; PostgreSQL; Docker; AWS",
        "español:nativo; inglés:b2",
        "Latinoamérica",
        "",
    ),  # noqa: E501
    (
        "train",
        "Ricardo Tanaka | ricardo.tanaka@mobile.com\nMobile dev. Android desde 2019, iOS desde 2022.\nStack: Kotlin, Jetpack Compose, Swift, SwiftUI, Firebase, Realm.\nTrabajo remoto.\nIdiomas: español nativo, inglés B2, japonés A2.\nIng. en Computación, 2019.",  # noqa: E501
        "Ricardo Tanaka",
        "ricardo.tanaka@mobile.com",
        "7",
        "Kotlin, Jetpack Compose, Swift, SwiftUI, Firebase, Realm",
        "Ingeniería en Computación",  # noqa: E501
        "",
        "Kotlin; Jetpack Compose; Swift; SwiftUI; Firebase",
        "español:nativo; inglés:b2; japonés:a2",
        "",
        "Mobile",
    ),  # noqa: E501
    (
        "val",
        "Valentina Aguirre\nvalentina.aguirre@data.uy\n\nMi área de expertise es la ingeniería de datos. He trabajado en el diseño de pipelines ETL para empresas de retail, procesando volúmenes de hasta 10TB diarios mediante Apache Spark, Airflow y herramientas del ecosistema Hadoop. También tengo experiencia en almacenes de datos analíticos sobre Snowflake y Redshift. Mi formación es en estadística (Licenciatura, UdelaR, 2018) y desde entonces (8 años) me dedico a esta práctica.\n\nResido en Montevideo. Hablo español como lengua materna e inglés a nivel C1.",  # noqa: E501
        "Valentina Aguirre",
        "valentina.aguirre@data.uy",
        "8",
        "Apache Spark, Airflow, Hadoop, Snowflake, Redshift, ETL",
        "Licenciatura en Estadística, UdelaR",  # noqa: E501
        "",
        "Spark:8; Airflow; Hadoop; Snowflake; Redshift",
        "español:nativo; inglés:c1",
        "Montevideo, Uruguay",
        "Retail",
    ),  # noqa: E501
    (
        "val",
        "R. Espinoza | r.espinoza@dev.pe\nPHP/Laravel dev | 4a en e-comm, 3a en gobierno\nStack: PHP, Laravel, MySQL, Redis, Vue.js\nES nat, EN B1\nLima, Perú\nTit: Ing. Sistemas, UNI",  # noqa: E501
        "R. Espinoza",
        "r.espinoza@dev.pe",
        "7",
        "PHP, Laravel, MySQL, Redis, Vue.js",
        "Ingeniería en Sistemas, UNI",  # noqa: E501
        "",
        "PHP:7; Laravel; MySQL; Redis; Vue.js",
        "español:nativo; inglés:b1",
        "Lima, Perú",
        "E-commerce",
    ),  # noqa: E501
    (
        "val",
        "Mauricio Esposito | mauricio.esposito@correo.com.ar\n\nSobre mí: nací en Rosario, soy fanático de Newell's, padre de mellizos, corro maratones (mejor marca 3h12) y hago asado los domingos. En lo profesional, soy desarrollador backend con 6 años de experiencia. Mi día a día actual se reparte entre escribir endpoints con FastAPI conectados a PostgreSQL, mantener containers Docker para nuestro stack de microservicios y atender deployments en AWS ECS. Trabajo en una fintech de medios de pago desde 2022 (antes pasé por una startup de delivery). Mi inglés llegó a nivel B2 después de un intercambio en Canadá. Vivo en Rosario.\n\nEdu: Ing. en Sistemas, UTN, 2020.",  # noqa: E501
        "Mauricio Esposito",
        "mauricio.esposito@correo.com.ar",
        "6",
        "Python, FastAPI, PostgreSQL, Docker, Microservicios, AWS ECS",
        "Ingeniería en Sistemas, UTN",  # noqa: E501
        "",
        "Python:6; FastAPI; PostgreSQL; Docker; AWS",
        "español:nativo; inglés:b2",
        "Rosario, Argentina",
        "Fintech",
    ),  # noqa: E501
    (
        "test",
        "Lukas Müller\nlukas.mueller@design.de\n\nUX/UI Designer with 5+ years of expertise in product design.\nTools: Figma, Sketch, Adobe XD, Principle, Lottie.\nProcess: I follow double diamond and design tokens methodology.\nIdiomas: alemán nativo, inglés C2, español B1.\nCurrently remote. Originally from Berlin.\nMFA Diseño Industrial, Universität der Künste Berlin, 2020.",  # noqa: E501
        "Lukas Müller",
        "lukas.mueller@design.de",
        "5",
        "Figma, Sketch, Adobe XD, Principle, Lottie, Diseño UX, Diseño UI",
        "MFA Diseño Industrial, Universität der Künste Berlin",  # noqa: E501
        "",
        "Figma; Sketch; Adobe XD",
        "alemán:nativo; inglés:c2; español:b1",
        "",
        "Diseño",
    ),
    (
        "test",
        "Constanza Rivas\nconstanza.rivas@correo.com.ar\n\nLlevo trabajando en backend Python desde mediados de 2021. Empecé en una agencia digital donde armé varios productos pequeños y desde 2024 estoy en una startup de logística donde diseño servicios sobre FastAPI con PostgreSQL como almacenamiento principal. Uso Docker para empaquetar y desplegar en AWS. Mi inglés es intermedio (B1, intento mejorarlo) y mi español es nativo. Vivo en Mendoza.\n\nEstudios: Licenciatura en Ciencias de la Computación, UNCuyo, 2021.",  # noqa: E501
        "Constanza Rivas",
        "constanza.rivas@correo.com.ar",
        "5",
        "Python, FastAPI, PostgreSQL, Docker, AWS",
        "Licenciatura en Ciencias de la Computación, UNCuyo",  # noqa: E501
        "",
        "Python:5; FastAPI; PostgreSQL; Docker; AWS",
        "español:nativo; inglés:b1",
        "Mendoza, Argentina",
        "Logística",
    ),  # noqa: E501
]

out = Path(__file__).resolve().parents[1] / "datasets" / "cv_profile.csv"
with out.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    for row in ORIGINALS + NEW + AMBIGUOUS:
        w.writerow(row)
total = len(ORIGINALS) + len(NEW) + len(AMBIGUOUS)
print(f"Escritas {total} filas en {out}")
print(f"  Originales: {len(ORIGINALS)}")
print(f"  Sinteticos claros: {len(NEW)}")
print(f"  Ambiguos: {len(AMBIGUOUS)}")
