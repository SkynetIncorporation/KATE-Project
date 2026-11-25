/* Datos de ejemplo. Después se reemplazan por el catálogo aprobado por el equipo. */
const PROFESORES = [
  {n:"Dra. Lucía Hernández",  d:"Ciencias Computacionales", m:"Análisis de algoritmos", e:4.7, r:32},
  {n:"Mtro. Jorge Salazar",   d:"Ciencias Computacionales", m:"Estructuras de datos",   e:3.2, r:18},
  {n:"Dr. Andrés Villalobos", d:"Ciencias Computacionales", m:"Bases de datos",         e:4.1, r:27},
  {n:"Mtra. Paola Ortega",    d:"Matemáticas",              m:"Cálculo diferencial",    e:4.9, r:41},
  {n:"Dr. Ricardo Núñez",     d:"Matemáticas",              m:"Álgebra lineal",         e:2.8, r:22},
  {n:"Mtra. Carmen Ibarra",   d:"Matemáticas",              m:"Matemáticas discretas",  e:3.9, r:15},
  {n:"Dr. Héctor Medina",     d:"Física",                   m:"Física general",         e:4.4, r:30},
  {n:"Mtro. Samuel Contreras",d:"Física",                   m:"Electromagnetismo",      e:3.5, r:12},
];
const DEPARTAMENTOS = [...new Set(PROFESORES.map(p => p.d))];

/* Cada materia: [ciclo, clave, nombre, créditos, prerrequisitos] */
const CARRERAS = [
  {id:"inco", nombre:"Ingeniería en Computación", materias:[
    [1,"MAT101","Cálculo diferencial",8,"-"],
    [1,"COM101","Programación básica",8,"-"],
    [1,"FIS101","Física general",8,"-"],
    [2,"MAT102","Álgebra lineal",8,"MAT101"],
    [2,"COM102","Estructuras de datos",8,"COM101"],
    [3,"MAT201","Matemáticas discretas",8,"MAT101"],
    [3,"COM201","Bases de datos",8,"COM102"],
    [4,"COM202","Análisis de algoritmos",8,"COM102, MAT201"],
    [4,"FIS201","Electromagnetismo",8,"FIS101"],
  ]},
  {id:"info", nombre:"Ingeniería Informática", materias:[
    [1,"MAT101","Cálculo diferencial",8,"-"],
    [1,"INF101","Fundamentos de programación",8,"-"],
    [2,"INF102","Estructuras de datos",8,"INF101"],
    [2,"MAT103","Matemáticas discretas",6,"MAT101"],
    [3,"INF201","Bases de datos",8,"INF102"],
    [3,"INF202","Redes de computadoras",8,"INF102"],
  ]},
];
