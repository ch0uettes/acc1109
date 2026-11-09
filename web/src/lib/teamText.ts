import type { Player, Position, SavedTeam, Team } from "./api";
import { captainId, POSITION_ORDER } from "./playerTable";

// Same shape as the server's TXT export (app/roster_export.py), for pasting
// straight into Discord.
const HIGH_TIERS = new Set(["MASTER", "GRANDMASTER", "CHALLENGER", "UNRANKED"]);

function tierLabel(p: Player | null): string {
  if (!p) return "알 수 없음";
  return HIGH_TIERS.has(p.tier) ? p.tier : `${p.tier} ${p.division}`;
}

interface Line {
  position: Position | null;
  player: Player | null;
  captain: boolean;
}

function render(teams: { index: number; lines: Line[] }[]): string {
  return teams
    .map((t) =>
      [
        `${t.index + 1}팀`,
        ...t.lines.map(
          (l) =>
            `${l.position ? `${l.position}: ` : ""}${l.player?.nickname ?? "알 수 없음"}${l.captain ? " [팀장]" : ""} (${tierLabel(l.player)})`
        ),
      ].join("\n")
    )
    .join("\n\n");
}

const byPosition = (a: { position: Position | null }, b: { position: Position | null }) =>
  POSITION_ORDER.indexOf(a.position ?? "TOP") - POSITION_ORDER.indexOf(b.position ?? "TOP");

export function generatedTeamsText(teams: Team[]): string {
  return render(
    teams.map((team) => {
      const cap = captainId(team.players);
      const lines: Line[] = team.slots
        ? team.slots.map((s) => ({ position: s.position, player: s.player, captain: s.player.id === cap }))
        : team.players.map((p) => ({ position: null, player: p, captain: p.id === cap }));
      return { index: team.index, lines: [...lines].sort(byPosition) };
    })
  );
}

export function savedTeamsText(teams: SavedTeam[]): string {
  return render(
    teams.map((team) => ({
      index: team.index,
      lines: team.entries.map((e) => ({
        position: e.position,
        player: e.player,
        captain: e.player != null && e.player.id === team.captain_player_id,
      })),
    }))
  );
}

// navigator.clipboard needs a secure context and permission; fall back to
// a hidden textarea + execCommand for anything else.
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }
}
