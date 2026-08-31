import Link from "next/link";
import type { SupporterPerk, SupporterTierInfo } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function loadPerks(): Promise<{ tiers: SupporterTierInfo[]; patreon_page_url?: string | null }> {
  try {
    const res = await fetch(`${API_BASE}/supporter/perks`, { next: { revalidate: 300 } });
    if (!res.ok) return { tiers: [] };
    return res.json();
  } catch {
    return { tiers: [] };
  }
}

function PerkList({ perks }: { perks: SupporterPerk[] }) {
  if (!perks.length) return <p className="text-sm text-muted">Perk list loading…</p>;
  return (
    <ul className="space-y-3">
      {perks.map((perk) => (
        <li key={perk.id} className="rounded-xl border border-border bg-elevated/40 px-4 py-3">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-medium text-fg">{perk.title}</p>
            {perk.status === "wip" && (
              <span className="shrink-0 rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-medium uppercase text-warning">
                WIP
              </span>
            )}
            {perk.status === "soon" && (
              <span className="shrink-0 rounded-full bg-muted/20 px-2 py-0.5 text-[10px] font-medium uppercase text-muted">
                Soon
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-muted">{perk.description}</p>
        </li>
      ))}
    </ul>
  );
}

export default async function GuideSupporterSection() {
  const data = await loadPerks();
  const base = data.tiers.find((tier) => tier.id === "supporter");
  const plus = data.tiers.find((tier) => tier.id === "supporter_plus");
  const patreonUrl = data.patreon_page_url?.trim();

  return (
    <section id="supporters" className="scroll-mt-24 space-y-6">
      <PartHeader title="Supporter perks" />
      <p className="text-sm leading-relaxed text-muted">
        War Queue is free to use. Optional Patreon support unlocks cosmetic and quality-of-life perks
        that sync when Discord is linked on Patreon.{" "}
        <Link href="/me/supporter" className="text-accent hover:underline">
          View your status
        </Link>
        .
      </p>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-border bg-panel p-5 shadow-panel">
          <h3 className="text-sm font-semibold text-fg">Supporter</h3>
          <p className="mt-1 text-xs text-muted">Base tier — queue peeking, profile styling, and planned Discord/recap perks.</p>
          <div className="mt-4">
            <PerkList perks={base?.perks ?? []} />
          </div>
        </div>
        <div className="rounded-2xl border border-[#4a3d6b] bg-[#2a2240]/50 p-5 shadow-panel">
          <h3 className="text-sm font-semibold text-[#e8dcff]">Supporter+</h3>
          <p className="mt-1 text-xs text-[#b8a8d8]">
            Everything in Supporter, plus vanity URLs, custom profile pictures, beta access, and a
            separate Discord Supporter+ role and profile flair.
          </p>
          <div className="mt-4">
            <PerkList perks={plus?.perks ?? []} />
          </div>
        </div>
      </div>

      {patreonUrl ? (
        <p className="text-sm text-muted">
          <a href={patreonUrl} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
            Support on Patreon
          </a>{" "}
          to unlock perks at launch.
        </p>
      ) : null}
    </section>
  );
}

function PartHeader({ title }: { title: string }) {
  return <h2 className="text-lg font-semibold text-fg">{title}</h2>;
}
