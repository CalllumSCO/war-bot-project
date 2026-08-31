"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getSupporterStatus, type SupporterStatus } from "@/lib/api";

function formatRenewalDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function membershipSubtitle(status: SupporterStatus): string {
  if (!status.active) return "Not active";
  const tier = status.tier_label ?? "Supporter";
  const patreonRenewal = formatRenewalDate(status.membership?.next_charge_date);
  const tempExpiry = formatRenewalDate(status.supporter_expires_at);
  if (patreonRenewal) return `${tier} — renews ${patreonRenewal}`;
  if (tempExpiry) return `${tier} — perks until ${tempExpiry}`;
  if (status.source === "env_override" || status.source === "admin") {
    return `${tier} — perks unlocked (manual)`;
  }
  return `${tier} — perks unlocked`;
}

export default function SupporterPage() {
  const router = useRouter();
  const [status, setStatus] = useState<SupporterStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const data = await getSupporterStatus();
        if (!mounted) return;
        setStatus(data);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setError("Couldn't load supporter status.");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [router]);

  if (loading) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <div className="h-8 w-48 animate-pulse rounded bg-elevated" />
        <div className="mt-6 h-40 animate-pulse rounded-2xl border border-border bg-panel" />
      </main>
    );
  }

  if (error || !status) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-sm text-danger">{error ?? "Something went wrong."}</p>
      </main>
    );
  }

  const patreonUrl = status.patreon_page_url?.trim();

  return (
    <main className="mx-auto max-w-2xl space-y-6 px-4 py-8">
      <div>
        <h1 className="text-xl font-semibold text-fg">Supporter</h1>
        <p className="mt-1 text-sm text-muted">
          Perks sync automatically when you support on Patreon with Discord linked.
        </p>
      </div>

      <section className="rounded-2xl border border-border bg-panel p-5 shadow-panel">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-fg">Membership</p>
            <p className="mt-0.5 text-sm text-muted">{membershipSubtitle(status)}</p>
            {status.membership?.patron_status && (
              <p className="mt-1 text-xs text-muted">
                Patreon status: {status.membership.patron_status.replace(/_/g, " ")}
              </p>
            )}
            {!status.active && status.membership && !status.membership.discord_id && (
              <p className="mt-2 text-xs text-warning">
                Connect Discord on your Patreon account so we can match your membership.
              </p>
            )}
          </div>
          {!status.active && patreonUrl && (
            <a
              href={patreonUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-hover"
            >
              Support on Patreon
            </a>
          )}
        </div>
      </section>

      {status.catalog?.tiers?.map((tier) => (
        <section key={tier.id} className="rounded-2xl border border-border bg-panel p-5 shadow-panel">
          <h2 className="text-sm font-semibold text-fg">{tier.label}</h2>
          {tier.includes && (
            <p className="mt-1 text-xs text-muted">Includes everything in Supporter.</p>
          )}
          <ul className="mt-4 space-y-3">
            {tier.perks.map((perk) => (
              <li key={perk.id}>
                <p className="text-sm font-medium text-fg">{perk.title}</p>
                <p className="mt-0.5 text-sm text-muted">{perk.description}</p>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {status.active && (
        <p className="text-xs text-muted">
          Customize colors on{" "}
          <Link href="/me/edit" className="text-accent hover:underline">
            Edit profile
          </Link>
          . Queue preview is available from the queue start screen.
        </p>
      )}
    </main>
  );
}
