import type { Payload, GraphicKind, PayloadOf } from "../contracts";
import {
  comparison, connection, h2h, heatMap, passNetwork, playerCard, scorebug, shotMap, situation, teamCard, timeline,
} from "./payloads";
import { standingsFull } from "./standings";

export * from "./payloads";
export * from "./standings";
export * from "./teams";
export { EDGE_FIXTURES } from "./edge";
export { SEASON_SCOPE } from "./helpers";

/** Un fixture por tipo de payload; el tipo `{ [K in GraphicKind]: PayloadOf<K> }` obliga a cubrir los 12 y a respetar el contrato. */
export const FIXTURES: { [K in GraphicKind]: PayloadOf<K> } = {
  player_card: playerCard,
  team_card: teamCard,
  pass_network: passNetwork,
  connection,
  shot_map: shotMap,
  heat_map: heatMap,
  comparison,
  standings: standingsFull,
  h2h,
  situation,
  timeline,
  scorebug,
};

export const ALL_FIXTURES: Payload[] = Object.values(FIXTURES);
