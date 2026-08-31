"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getPublicPatrons, type PublicPatron } from "@/lib/api";

export default function PatronFooter() {
  const [patrons, setPatrons] = useState<PublicPatron[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getPublicPatrons()
      .then((rows) => {
        if (!cancelled) setPatrons(rows);
      })
      .catch(() => {
        if (!cancelled) setPatrons([]);
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!loaded || !patrons.length) return null;

  return (
    <section className="mt-10 rounded-2xl border border-[#4a3d6b] bg-[#2a2240]/80 px-5 py-5">
      <h2 className="text-sm font-semibold text-[#d8c8ff]">Thank you to our patrons</h2>
      <p className="mt-1 text-xs text-[#b8a8d8]">
        War Queue is supported by the community. These players help keep the service running.
      </p>
      <ul className="mt-4 flex flex-wrap gap-x-3 gap-y-2 text-sm">
        {patrons.map((patron) => (
          <li key={patron.discord_id}>
            <Link
              href={patron.profile_path}
              className="font-medium text-[#e8dcff] underline-offset-2 transition hover:text-white hover:underline"
            >
              {patron.display_name}
              {patron.tier === "supporter_plus" ? (
                <span className="ml-1 text-xs text-[#c9b0ff]">+</span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
