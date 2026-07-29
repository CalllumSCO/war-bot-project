import ProfileView from "@/components/ProfileView";
import { getPublicProfile, type PublicProfile } from "@/lib/api";

export default async function PublicProfilePage({
  params,
}: {
  params: Promise<{ discordId: string }>;
}) {
  const { discordId } = await params;

  let profile: PublicProfile | null = null;
  try {
    profile = await getPublicProfile(discordId);
  } catch {
    profile = null;
  }

  if (!profile) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-12 text-center">
        <p className="text-sm text-muted">This profile isn&apos;t available.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <ProfileView profile={profile} />
    </main>
  );
}
