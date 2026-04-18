/**
 * Per-bus-type colour tokens used in both SignalTree badges and
 * the MetadataPanel Bus Frames section.
 */
export interface BusColor {
  text:   string;   // label / badge text
  bg:     string;   // badge background
  border: string;   // badge border
}

export const BUS_COLORS: Record<string, BusColor> = {
  "CAN":      { text: "#5b9cf6", bg: "#0e1824", border: "#1a2e4a" },
  "CAN FD":   { text: "#38bdf8", bg: "#081c2a", border: "#0f2e3e" },
  "LIN":      { text: "#4ade80", bg: "#0a2016", border: "#143228" },
  "MOST":     { text: "#b77ff0", bg: "#180d28", border: "#281840" },
  "FlexRay":  { text: "#fb923c", bg: "#221408", border: "#3a2410" },
  "Ethernet": { text: "#2dd4bf", bg: "#08201e", border: "#0e3030" },
  "K-Line":   { text: "#f0c040", bg: "#201c04", border: "#302c08" },
  "USB":      { text: "#f07070", bg: "#200808", border: "#301410" },
};

/** Returns the colour tokens for a bus type, with a neutral fallback. */
export function busColor(type: string): BusColor {
  return BUS_COLORS[type] ?? { text: "#888888", bg: "#1e1e1e", border: "#333333" };
}
