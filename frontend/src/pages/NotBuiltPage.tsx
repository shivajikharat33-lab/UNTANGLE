import { Alert } from "../components/Alert";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";

type NotBuiltPageProps = {
  title: string;
  description: string;
};

export function NotBuiltPage({ title, description }: NotBuiltPageProps) {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="Not built yet" title={title} description={description} />
      <Alert tone="info" title="Not built yet">
        This screen does not load drawings, run checks, or show results.
      </Alert>
      <div className="mt-6">
        <EmptyState title="Nothing to show" description="There is no project data on this page because that work has not been built." />
      </div>
    </div>
  );
}
