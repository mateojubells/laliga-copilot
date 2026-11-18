import { player, team } from "./helpers";

// Equipos de LaLiga 2024-25. Los colores son aproximados y los escudos se generan en cliente (no hay escudos reales).
export const BARCELONA = team("barcelona", "FC Barcelona", "BAR", "#A50044", "#004D98");
export const VALLADOLID = team("valladolid", "Real Valladolid", "VLL", "#5E2D91", "#FFFFFF");

export const LEAGUE_TEAMS = {
  barcelona: BARCELONA,
  valladolid: VALLADOLID,
  real_madrid: team("real_madrid", "Real Madrid", "RMA", "#FFFFFF", "#FEBE10", "#0b1018"),
  atletico: team("atletico", "Atlético de Madrid", "ATM", "#CB3524", "#272E61"),
  athletic: team("athletic", "Athletic Club", "ATH", "#EE2523", "#FFFFFF"),
  villarreal: team("villarreal", "Villarreal CF", "VIL", "#FBE10F", "#005187", "#0b1018"),
  betis: team("betis", "Real Betis", "BET", "#0BB363", "#FFFFFF"),
  celta: team("celta", "RC Celta", "CEL", "#8AC3EE", "#E5254B", "#0b1018"),
  rayo: team("rayo", "Rayo Vallecano", "RAY", "#FFFFFF", "#E53027", "#0b1018"),
  osasuna: team("osasuna", "CA Osasuna", "OSA", "#D91A21", "#0A346F"),
  mallorca: team("mallorca", "RCD Mallorca", "MLL", "#E20613", "#000000"),
  real_sociedad: team("real_sociedad", "Real Sociedad", "RSO", "#0067B1", "#FFFFFF"),
  getafe: team("getafe", "Getafe CF", "GET", "#005999", "#FFFFFF"),
  girona: team("girona", "Girona FC", "GIR", "#EE1C25", "#FFFFFF"),
  sevilla: team("sevilla", "Sevilla FC", "SEV", "#FFFFFF", "#D4021D", "#0b1018"),
  espanyol: team("espanyol", "RCD Espanyol", "ESP", "#007FC8", "#FFFFFF"),
  alaves: team("alaves", "Deportivo Alavés", "ALA", "#0761AF", "#FFFFFF"),
  leganes: team("leganes", "CD Leganés", "LEG", "#1C5CAB", "#FFFFFF"),
  las_palmas: team("las_palmas", "UD Las Palmas", "LPA", "#FFE400", "#0064AA", "#0b1018"),
  valencia: team("valencia", "Valencia CF", "VAL", "#FFFFFF", "#EE7F00", "#0b1018"),
};

const B = BARCELONA;
const V = VALLADOLID;

// Barcelona (nombres reales de la plantilla 2024-25; dorsales orientativos)
export const SZCZESNY = player("szczesny", "Wojciech Szczęsny", "Szczęsny", 25, "GK", B);
export const KOUNDE = player("kounde", "Jules Koundé", "Koundé", 23, "RB", B);
export const CUBARSI = player("cubarsi", "Pau Cubarsí", "Cubarsí", 2, "CB", B);
export const INIGO = player("inigo-martinez", "Íñigo Martínez", "Íñigo Martínez", 5, "CB", B);
export const BALDE = player("balde", "Alejandro Balde", "Balde", 3, "LB", B);
export const DE_JONG = player("de-jong", "Frenkie de Jong", "De Jong", 21, "DM", B);
export const PEDRI = player("pedri", "Pedro González López", "Pedri", 8, "CM", B);
export const OLMO = player("dani-olmo", "Daniel Olmo", "Dani Olmo", 20, "AM", B);
export const LAMINE = player("lamine-yamal", "Lamine Yamal", "Lamine Yamal", 19, "RW", B);
export const LEWANDOWSKI = player("lewandowski", "Robert Lewandowski", "Lewandowski", 9, "ST", B);
export const RAPHINHA = player("raphinha", "Raphael Dias Belloli", "Raphinha", 11, "LW", B);
export const FERMIN = player("fermin", "Fermín López", "Fermín", 16, "AM", B);

// Valladolid
export const HEIN = player("karl-hein", "Karl Hein", "Karl Hein", 1, "GK", V);
export const JUMA = player("juma-bah", "Juma Bah", "Juma Bah", 15, "CB", V);
export const JURIC = player("juric", "Stanko Jurić", "Juric", 8, "CM", V);
export const MARCOS_ANDRE = player("marcos-andre", "Marcos André", "Marcos André", 9, "ST", V);
export const RAUL_MORO = player("raul-moro", "Raúl Moro", "Raúl Moro", 17, "LW", V);

// ---- Casos límite (galería ?case=edge): colores y nombres incómodos. Cifras y nombres de prueba, no datos reales.
/** Primario MUY OSCURO (azul casi negro) con nombre largo: el color del club apenas se distingue del cristal del panel. */
export const SOCIEDAD_FUTBOL = team("real_sociedad_futbol", "Real Sociedad de Fútbol", "RSO", "#0A1A3A", "#FFFFFF");
/** Primario MUY CLARO (blanco): el texto va en oscuro y el filete del club desaparece sobre fondos claros. */
export const MADRID_CLARO = LEAGUE_TEAMS.real_madrid;
export const INIGO_V = player("inigo-martinez-berridi", "Íñigo Martínez Berridi", "Íñigo Martínez Berridi", 4, "CB", V);
export const TER_STEGEN_V = player("ter-stegen", "Marc-André ter Stegen", "Marc-André ter Stegen", 1, "GK", V);
export const JUGADOR_SIN_DORSAL = player("sin-dorsal", "Abde Ezzalzouli Ezzalzouli", "Abde Ezzalzouli", null, "RW", LEAGUE_TEAMS.real_madrid);
