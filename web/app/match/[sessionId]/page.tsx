import MatchClient from "./MatchClient";

export default async function MatchPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <MatchClient sessionId={sessionId} />;
}
