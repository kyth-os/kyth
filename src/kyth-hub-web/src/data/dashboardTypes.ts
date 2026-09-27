// Shapes the Dashboard's cards render. These started life alongside
// fixture data, back when the Hub was a prototype with no backend; the
// fixtures are gone now — every value on the Dashboard comes from a live
// read in services/liveData.ts, or renders as "no reading yet". Only the
// types remain, because the components still need to agree on a shape.

export interface StatTile {
  label: string;
  value: string;
  delta?: string;
  deltaTone?: "ok" | "warn" | "error";
}

export interface GuardianEvent {
  title: string;
  detail: string;
  status: "ok" | "warn" | "error";
  when: string;
  recipeId: string | null;
  action: string;
  verified: boolean | null;
}
