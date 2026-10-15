import { Link, useParams } from "react-router";
import { FindingsPanel } from "../components/FindingsPanel";
import { EmptyState } from "../components/EmptyState";
import { buttonClass } from "../lib/buttonClass";

export function FindingsPage() {
  const { id } = useParams();
  if (!id) {
    return <EmptyState title="No project was selected" description="Open a project from the dashboard." />;
  }
  return (
    <div className="space-y-6">
      <FindingsPanel jobId={id} checkStatus="done" />
      <Link to={`/app/projects/${id}/processing`} className={buttonClass("ghost")}>Back to processing</Link>
    </div>
  );
}
