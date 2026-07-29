import { redirect } from "next/navigation";
import { getInvitePreview, joinGroupByCode, type InvitePreview } from "@/lib/api";
import PlayerRow from "@/components/PlayerRow";

export default async function InviteLinkPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;

  let preview: InvitePreview | null = null;
  let loadError = false;
  try {
    preview = await getInvitePreview(code);
  } catch {
    loadError = true;
  }

  async function joinAction() {
    "use server";
    await joinGroupByCode(code);
    redirect("/q");
  }

  return (
    <main className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-panel p-6 shadow-panel">
        <h1 className="text-center text-lg font-semibold text-fg">Group invite</h1>

        {loadError || !preview ? (
          <p className="mt-4 text-center text-sm text-muted">
            This invite link is invalid or has expired.
          </p>
        ) : preview.expired ? (
          <p className="mt-4 text-center text-sm text-muted">
            This invite link has expired.
          </p>
        ) : (
          <>
            <p className="mt-2 text-center text-sm text-muted">
              You&apos;ve been invited to join:
            </p>
            <div className="mt-4 space-y-2">
              {preview.fromPlayers.map((player) => (
                <PlayerRow key={player.discordId} player={player} showSr />
              ))}
            </div>
            <form action={joinAction}>
              <button
                type="submit"
                className="mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-hover"
              >
                Join group
              </button>
            </form>
          </>
        )}
      </div>
    </main>
  );
}
